"""批次后台执行器。

为什么用一个线程而不是 `BackgroundTasks`：`BackgroundTasks` 挂在响应之后执行，
进程一重启任务就蒸发，批次会永久停在 processing——这正是 docs/08 A12 点名不许
出现的情况。这里改成"入库 + 轮询认领"：

1. 上传接口只负责把批次写成 `uploaded` 并立刻返回 202；
2. worker 每 `import_worker_poll_seconds` 扫一次 `uploaded`，用条件 UPDATE
   原子认领（`WHERE status='uploaded'`，rowcount==1 才算抢到）；
3. 认领成功后解析、分类、写草稿，最后转 `pending_review` 或 `failed`。

这样即使请求进程挂了，批次也只是留在 `uploaded` 等下一次启动继续跑。

**已知限制（写在代码里而不是藏着）**：启动时的"中断恢复"会把所有 `processing`
批次判为 `failed(BATCH_INTERRUPTED)`。这假设只有一个后端进程正在处理导入
（当前 docker-compose 与初赛部署就是一个 app 容器）。如果以后要横向扩多副本，
必须把恢复逻辑改成"按 started_at 超时"而不是"启动即全清"，否则 A 副本启动会
杀掉 B 副本正在跑的批次。巡检 `_sweep` 已经是按超时判断的，扩副本时复用它即可。
"""

from __future__ import annotations

import logging
import threading
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from .. import models
from ..config import Settings
from ..db import as_utc, utcnow
from ..intelligence.base import IntelligenceProvider
from . import imports

logger = logging.getLogger("app.import_worker")

# 空闲多少轮巡检一次滞留批次（按默认 0.5s 轮询约 10 秒）
_SWEEP_EVERY_IDLE_TICKS = 20


class ImportWorker:
    """单线程批次执行器。start()/stop() 由应用 lifespan 负责调用。"""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        provider: IntelligenceProvider,
        settings: Settings,
    ) -> None:
        self._factory = session_factory
        self._provider = provider
        self._settings = settings
        self._key = settings.data_encryption_key
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._idle_ticks = 0

    # ---- 生命周期 ----

    def start(self) -> None:
        recovered = self.recover_interrupted()
        if recovered:
            logger.warning("启动恢复：%s 个中断批次已标为 failed 并可重试", recovered)
        self._thread = threading.Thread(
            target=self._loop, name="import-worker", daemon=True
        )
        self._thread.start()
        logger.info(
            "批次执行器已启动 provider=%s poll=%.1fs",
            getattr(self._provider, "name", "unknown"),
            self._settings.import_worker_poll_seconds,
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    # ---- 主循环 ----

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                worked = self.tick()
            except Exception:  # 线程不能因为一次异常就死掉，否则上传全变僵尸
                logger.exception("批次执行器本轮出错，下轮继续")
                worked = False

            if worked:
                self._idle_ticks = 0
                continue

            self._idle_ticks += 1
            if self._idle_ticks % _SWEEP_EVERY_IDLE_TICKS == 0:
                try:
                    self.sweep()
                except Exception:
                    logger.exception("滞留批次巡检失败")
            self._stop.wait(self._settings.import_worker_poll_seconds)

    def tick(self) -> bool:
        """认领并处理一个批次。返回 False 表示当前没有待处理批次。"""
        batch_id = self._claim_next()
        if batch_id is None:
            return False

        db = self._factory()
        try:
            batch = db.get(models.ImportBatch, batch_id)
            if batch is None:  # 认领后被删，没什么可做的
                return True
            imports.process_batch(db, batch, self._provider, self._settings)
        except Exception:
            # process_batch 内部已兜住业务失败；这里兜的是"写库本身炸了"这类
            # 未预期异常，同样必须给批次终态
            logger.exception("处理批次 %s 失败", batch_id)
            db.rollback()
            try:
                batch = db.get(models.ImportBatch, batch_id)
                if batch is not None and batch.status in (
                    imports.STATUS_PROCESSING,
                    imports.STATUS_UPLOADED,
                ):
                    imports.mark_failed(
                        db,
                        batch,
                        "INTERNAL_ERROR",
                        "服务内部错误导致处理中断，请点击重试",
                        self._key,
                    )
            except Exception:
                logger.exception("写回批次 %s 的失败状态也失败了", batch_id)
        finally:
            db.close()
        return True

    # ---- 认领 ----

    def _claim_next(self) -> str | None:
        db = self._factory()
        try:
            candidate = db.scalar(
                select(models.ImportBatch.id)
                .where(models.ImportBatch.status == imports.STATUS_UPLOADED)
                .order_by(models.ImportBatch.created_at)
                .limit(1)
            )
            if candidate is None:
                return None

            now = utcnow()
            # 条件 UPDATE 就是这里的锁：只有把 uploaded 改成 processing 的那一方
            # rowcount==1，其余进程下一轮自然看到 processing 而跳过
            claimed = db.execute(
                update(models.ImportBatch)
                .where(
                    models.ImportBatch.id == candidate,
                    models.ImportBatch.status == imports.STATUS_UPLOADED,
                )
                .values(
                    status=imports.STATUS_PROCESSING,
                    started_at=now,
                    updated_at=now,
                    version=models.ImportBatch.version + 1,
                )
            ).rowcount
            db.commit()
            return candidate if claimed == 1 else None
        finally:
            db.close()

    # ---- 恢复与巡检 ----

    def recover_interrupted(self) -> int:
        """启动时把上一次进程留下的 processing 批次标 failed，允许重试。

        不做"自动接着跑"：原文件还在，但用户此时多半已经走开了，悄悄重跑会在
        他回来时突然多出一个待确认批次。标 failed 让用户自己决定更诚实。
        """
        db = self._factory()
        try:
            rows = db.scalars(
                select(models.ImportBatch).where(
                    models.ImportBatch.status == imports.STATUS_PROCESSING
                )
            ).all()
            for batch in rows:
                imports.mark_failed(
                    db,
                    batch,
                    imports.BATCH_INTERRUPTED,
                    "服务重启中断了本次处理，请点击重试",
                    self._key,
                )
            if rows:
                db.commit()
            return len(rows)
        finally:
            db.close()

    def sweep(self) -> int:
        """把超过批次期限仍没结束的批次转成 failed。

        docs/13：整体批次期限 300 秒。这道巡检是"永久 processing"的最后一道
        防线——即便认领后进程卡死，也会在期限后被收掉。
        """
        deadline = timedelta(seconds=self._settings.batch_deadline_seconds)
        now = utcnow()
        db = self._factory()
        try:
            rows = db.scalars(
                select(models.ImportBatch).where(
                    models.ImportBatch.status.in_(
                        [imports.STATUS_PROCESSING, imports.STATUS_UPLOADED]
                    )
                )
            ).all()
            expired = [
                batch
                for batch in rows
                if (as_utc(batch.started_at) or as_utc(batch.created_at)) < now - deadline
            ]
            for batch in expired:
                imports.mark_failed(
                    db,
                    batch,
                    imports.BATCH_TIMEOUT,
                    "批次处理超时，请点击重试",
                    self._key,
                )
            if expired:
                db.commit()
                logger.warning("巡检：%s 个批次超时转 failed", len(expired))
            return len(expired)
        finally:
            db.close()
