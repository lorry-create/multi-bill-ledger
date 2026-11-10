"""已确认交易的查询、纠错与个人商户规则。

这个文件只做三件事：读已有交易、改一条交易、按商户沉淀个人规则。
报表汇总**不在这里**——统一口径在 `services/reporting.py`，这里只保证
"吐出去的行"和"存进去的行"逐字段一致。

三条纪律：

1. **不推断分类来源**。库里没记就如实返回 `pending` 加一句说明，绝不因为
   类别名字看起来像某类就标 `general_rule` 或 `deepseek`——那是伪造证据，
   docs/20 第一节已明确禁止。
2. **去重摘要在编辑后不重算**。`dedupe_digest` 标识的是"这次导入的哪一行"
   （见 services/dedupe.py），不是内容哈希。用户改了金额就重算，等于把
   原记录的去重身份换掉，同一份账单再导入一次会重新进账。
3. **金额只在加密区**。表上只有月/类别/流向/平台这些索引列，所以日期区间
   过滤和排序只能解密后在内存里做。个人规模（万级以内）可接受，数据量再涨
   要改成独立存储或加明文日期索引，不能在加密列上假装能 SQL 排序。
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..contracts import (
    ClassificationSource,
    ErrorDetails,
    FieldError,
    ResolvedCategory,
    Transaction,
    TransactionPage,
    TransactionPatch,
)
from ..crypto import CryptoError, decrypt_json, encrypt_json
from ..db import utcnow
from ..errors import ApiError
from ..intelligence.normalize import normalize_merchant
from .dedupe import day_key, flow_value, month_index

logger = logging.getLogger("app.services.transactions")

STATUS_CONFIRMED = "confirmed"

# 历史记录（CHG-004 之前入账的）加密区里没有这两项。缺了就照实说明，
# 不拿当前规则"补记"一个当时并不存在的分类来源。
_MISSING_SOURCE_REASON = "该记录入账时未保存分类来源"

# 契约里 category 允许 pending，但个人规则只接受明确类别
_RULE_CATEGORIES = {item.value for item in ResolvedCategory}


def _not_found() -> ApiError:
    # 别人的交易一律 404 而不是 403：403 等于告诉调用方"这个 ID 确实存在"
    return ApiError("RESOURCE_NOT_FOUND", 404, "资源不存在", ErrorDetails())


def _unprocessable(field: str, code: str, message: str) -> ApiError:
    return ApiError(
        "VALIDATION_ERROR",
        422,
        message,
        ErrorDetails(fields=[FieldError(field=field, row_id=None, code=code, message=message)]),
    )


def _parse_occurred_at(raw: object) -> datetime | None:
    if isinstance(raw, datetime):
        return raw
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _batch_methods(db: Session, batch_ids: set[str]) -> dict[str, str]:
    """加密区没存采集方式时回查批次表。一次批量查完，不做 N+1。"""
    if not batch_ids:
        return {}
    rows = db.execute(
        select(models.ImportBatch.id, models.ImportBatch.ingestion_method).where(
            models.ImportBatch.id.in_(batch_ids)
        )
    ).all()
    return {row[0]: row[1] for row in rows}


def to_contract(
    record: models.Transaction,
    payload: dict,
    *,
    ingestion_method: str,
) -> Transaction:
    """库行 + 解密载荷 → 契约 Transaction。

    调用方必须已确认 `payload` 里有可用的 `occurred_at`：确认入账时它是必填的，
    真缺了就说明这条记录坏了，应当跳过而不是造一个时间出来。
    """
    source_raw = payload.get("classification_source") or ClassificationSource.pending.value
    return Transaction.model_validate(
        {
            "source_transaction_id": payload.get("source_transaction_id"),
            "occurred_at": payload.get("occurred_at"),
            "amount_fen": payload.get("amount_fen"),
            # 初赛只支持 CNY，入账时必填；历史记录缺了就只能是唯一合法值
            "currency": payload.get("currency") or "CNY",
            "flow_type": payload.get("flow_type") or record.flow_type,
            "merchant": payload.get("merchant") or "",
            "description": payload.get("description") or "",
            "category": payload.get("category") or record.category,
            "id": record.id,
            "version": record.version,
            "source": record.source,
            "ingestion_method": ingestion_method,
            # 批次被删除后外键为 NULL，契约里这个字段不可空，只能给空串
            "import_batch_id": record.import_batch_id or "",
            "classification_source": source_raw,
            "classification_reason": payload.get("classification_reason")
            or (_MISSING_SOURCE_REASON if source_raw == ClassificationSource.pending.value else ""),
            "status": STATUS_CONFIRMED,
        }
    )


def _decoded_rows(
    db: Session,
    user_id: str,
    key: str,
    *,
    category: object,
    source: object,
    flow_type: object,
) -> list[tuple[models.Transaction, dict]]:
    """取本人已确认交易并解密。索引列能在 SQL 过滤，日期与排序只能在内存做。"""
    stmt = select(models.Transaction).where(
        models.Transaction.user_id == user_id,
        models.Transaction.status == STATUS_CONFIRMED,
    )
    if category is not None:
        stmt = stmt.where(models.Transaction.category == str(getattr(category, "value", category)))
    if source is not None:
        stmt = stmt.where(models.Transaction.source == str(getattr(source, "value", source)))
    if flow_type is not None:
        stmt = stmt.where(
            models.Transaction.flow_type == str(getattr(flow_type, "value", flow_type))
        )

    decoded: list[tuple[models.Transaction, dict]] = []
    for record in db.scalars(stmt).all():
        try:
            payload = decrypt_json(key, record.encrypted_payload)
        except CryptoError:
            # 单条坏了不该让整页 500；缺的条数会体现在 total 里，运维去查日志
            logger.warning("交易 %s 载荷无法解密，已跳过列表返回", record.id)
            continue
        if _parse_occurred_at(payload.get("occurred_at")) is None:
            logger.warning("交易 %s 缺少可解析的 occurred_at，已跳过列表返回", record.id)
            continue
        decoded.append((record, payload))
    return decoded


def filtered_rows(
    db: Session,
    user_id: str,
    key: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    category: object = None,
    source: object = None,
    flow_type: object = None,
) -> list[tuple[models.Transaction, dict, datetime]]:
    """筛选 + 解密 + 倒序。**列表页与 CSV 导出共用这一份实现。**

    导出如果自己再写一套筛选，迟早出现"页面 12 条、CSV 15 条"这种谁也说不清的
    问题（docs/08 A11 明确要求导出范围与页面数字一致）。所以这里只做"筛选"，
    分页交给调用方——列表取窗口，导出取全量。
    """
    if date_from and date_to and date_from > date_to:
        raise _unprocessable("date_from", "DATE_RANGE_REVERSED", "date_from 不能晚于 date_to")

    decoded = _decoded_rows(
        db, user_id, key, category=category, source=source, flow_type=flow_type
    )

    lower = date_from.isoformat() if date_from else None
    upper = date_to.isoformat() if date_to else None
    kept: list[tuple[models.Transaction, dict, datetime]] = []
    for record, payload in decoded:
        occurred = _parse_occurred_at(payload.get("occurred_at"))
        assert occurred is not None  # _decoded_rows 已保证
        local_day = day_key(occurred)
        if lower and local_day < lower:
            continue
        if upper and local_day > upper:
            continue
        kept.append((record, payload, occurred))

    # 契约：occurred_at 倒序，再 id 倒序。id 兜底是为了同一秒的多笔记录顺序稳定
    kept.sort(key=lambda item: (item[2].astimezone(), item[0].id), reverse=True)
    return kept


def list_transactions(
    db: Session,
    user_id: str,
    key: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    category: object = None,
    source: object = None,
    flow_type: object = None,
    page: int = 1,
    page_size: int = 50,
) -> TransactionPage:
    """按上海自然日筛选 + 分页。两端都含边界，与契约描述一致。"""
    kept = filtered_rows(
        db,
        user_id,
        key,
        date_from=date_from,
        date_to=date_to,
        category=category,
        source=source,
        flow_type=flow_type,
    )

    total = len(kept)
    start = (page - 1) * page_size
    window = kept[start : start + page_size]

    methods = _batch_methods(db, {r.import_batch_id for r, _, _ in window if r.import_batch_id})
    items = [
        to_contract(
            record,
            payload,
            ingestion_method=payload.get("ingestion_method")
            or methods.get(record.import_batch_id or "", "file"),
        )
        for record, payload, _ in window
    ]
    return TransactionPage(items=items, total=total, page=page, page_size=page_size)


def load_owned(db: Session, user_id: str, transaction_id: str) -> models.Transaction:
    record = db.get(models.Transaction, transaction_id)
    if record is None or record.user_id != user_id:
        raise _not_found()
    return record


def _merge_changes(payload: dict, changes: dict) -> dict:
    """只覆盖请求里显式出现的键。`exclude_unset` 由调用方保证。

    枚举必须取 `.value`。Pydantic 把请求体里的 "dining" 解析成 `Category.dining`，
    直接塞回载荷会写成 `"Category.dining"`——加密区里存下的就成了脏值，报表
    分类统计会整块归到"未知类别"，而且因为它在加密区里，SQL 也查不出来。
    """
    merged = dict(payload)
    for field, value in changes.items():
        if isinstance(value, datetime):
            merged[field] = value.isoformat()
        elif isinstance(value, Enum):
            merged[field] = value.value
        else:
            merged[field] = value
    return merged


def _upsert_rule(
    db: Session,
    key: str,
    *,
    user_id: str,
    source: str,
    merchant: str,
    category: str,
) -> str | None:
    """按（本人 + 平台 + 标准化商户）建立或更新个人规则，返回规则 ID。

    规则表没有明文商户列（匹配条件本身是敏感信息，见 docs/13），所以只能
    先取本人该平台的全部规则再解密比对。个人规则通常几十条，可以接受。
    """
    normalized = normalize_merchant(merchant)
    if not normalized:
        return None

    existing: models.ClassificationRule | None = None
    for rule in db.scalars(
        select(models.ClassificationRule).where(
            models.ClassificationRule.user_id == user_id,
            models.ClassificationRule.source == source,
        )
    ).all():
        try:
            rule_payload = decrypt_json(key, rule.encrypted_payload)
        except CryptoError:
            continue
        if rule_payload.get("merchant_normalized") == normalized:
            existing = rule
            break

    if existing is not None:
        existing.encrypted_payload = encrypt_json(
            key,
            {
                "merchant_normalized": normalized,
                "category": category,
                # 停用的规则被用户重新"记住"时应当重新生效
                "enabled": True,
            },
        )
        existing.enabled = True
        existing.version += 1
        existing.updated_at = utcnow()
        return existing.id

    rule = models.ClassificationRule(
        id=str(uuid.uuid4()),
        user_id=user_id,
        source=source,
        version=1,
        enabled=True,
        encrypted_payload=encrypt_json(
            key,
            {"merchant_normalized": normalized, "category": category, "enabled": True},
        ),
    )
    db.add(rule)
    return rule.id


def patch_transaction(
    db: Session,
    key: str,
    *,
    user_id: str,
    transaction_id: str,
    patch: TransactionPatch,
) -> Transaction:
    """修改一条交易，可选同时沉淀个人商户规则。

    顺序：归属校验 → 版本校验 → 合并字段 → 写库 → 记纠错日志 → 建规则，
    全部在一个事务里，任何一步失败都不留下半条修改。
    """
    record = load_owned(db, user_id, transaction_id)

    if patch.expected_version != record.version:
        raise ApiError(
            "VERSION_CONFLICT",
            409,
            "记录已被其他操作修改",
            ErrorDetails(current_version=record.version),
        )

    try:
        payload = decrypt_json(key, record.encrypted_payload)
    except CryptoError:
        raise ApiError("INTERNAL_ERROR", 500, "该记录无法解密，请联系管理员") from None

    # exclude_unset：只有请求体里真正写了的字段才改，其余保持原值
    changes = patch.changes.model_dump(exclude_unset=True, mode="python")

    if "occurred_at" in changes and changes["occurred_at"] is not None:
        if changes["occurred_at"].tzinfo is None:
            raise _unprocessable(
                "changes.occurred_at",
                "TIME_WITHOUT_TIMEZONE",
                "交易时间必须带时区，例如 2026-11-08T12:00:00+08:00",
            )

    merged = _merge_changes(payload, changes)

    # 显式改了类别才标 manual；没提交 category 就保留原类别与来源
    if changes.get("category") is not None:
        new_category = str(getattr(changes["category"], "value", changes["category"]))
        if new_category != payload.get("category"):
            merged["category"] = new_category
            merged["classification_source"] = ClassificationSource.manual.value
            merged["classification_reason"] = "用户手动修正分类"

    before = {field: payload.get(field) for field in merged if payload.get(field) != merged.get(field)}

    occurred = _parse_occurred_at(merged.get("occurred_at"))
    if occurred is None:
        raise _unprocessable("changes.occurred_at", "TIME_MISSING", "交易时间不能为空")

    if before:
        # 索引列必须跟着改，否则按类别/月份筛选和报表会立刻对不上
        record.month_index = month_index(occurred)
        record.category = str(merged.get("category") or record.category)
        record.flow_type = flow_value(merged.get("flow_type") or record.flow_type)
        record.encrypted_payload = encrypt_json(key, merged)
        record.version += 1
        record.updated_at = utcnow()

    rule_id: str | None = None
    if patch.remember_rule:
        # 契约：只在非空商户和非 pending 类别时生效，否则静默跳过而不是报错。
        # 注意这一步不能因为"交易字段没变"被跳过——用户可能只是点了「记住商户」，
        # 类别本来就是对的，这时该建的规则照样要建。
        merchant = str(merged.get("merchant") or "")
        category_value = str(merged.get("category") or "")
        if merchant.strip() and category_value in _RULE_CATEGORIES:
            rule_id = _upsert_rule(
                db,
                key,
                user_id=user_id,
                source=record.source,
                merchant=merchant,
                category=category_value,
            )

    if not before and rule_id is None:
        # 提交内容与原值完全相同，也没有要新建的规则：不动版本。
        # 改了又改回原值不该让前端手里的 expected_version 失效。
        return to_contract(
            record,
            payload,
            ingestion_method=payload.get("ingestion_method") or "file",
        )

    db.add(
        models.CorrectionLog(
            id=str(uuid.uuid4()),
            user_id=user_id,
            transaction_id=record.id,
            rule_created=rule_id is not None,
            # 修改前后的值都是敏感内容，整段进加密区
            encrypted_payload=encrypt_json(
                key,
                {
                    "before": before,
                    "after": {field: merged.get(field) for field in before},
                    "rule_id": rule_id,
                },
            ),
        )
    )
    db.commit()
    db.refresh(record)

    return to_contract(
        record,
        merged,
        ingestion_method=merged.get("ingestion_method") or "file",
    )


__all__ = [
    "STATUS_CONFIRMED",
    "filtered_rows",
    "list_transactions",
    "load_owned",
    "patch_transaction",
    "to_contract",
]
