"""分类月预算的写入。

只有写入这一件事：读预算的汇总逻辑统一在 `services/reporting.py` 的
`_budget_statuses()`，这里不要去算"用了多少"，否则又会出现两套口径。

金额进加密区，表上只留 user_id / month / category 三列做唯一键与查询索引——
和 transactions 的保护方式一致（docs/13）。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..contracts import Budget, BudgetInput, ResolvedCategory
from ..crypto import CryptoError, decrypt_json, encrypt_json
from ..db import utcnow


def put_budget(db: Session, key: str, *, user_id: str, payload: BudgetInput) -> Budget:
    """按（用户, 月份, 类别）覆盖写入，契约要求始终 200。

    同一键并发写会撞唯一约束：先查后写之间别的事务可能插进来，所以捕
    IntegrityError 后重查一次改走更新，而不是把 500 抛给前端。
    """
    category = payload.category.value if isinstance(payload.category, ResolvedCategory) else str(payload.category)

    def _find() -> models.Budget | None:
        return db.scalar(
            select(models.Budget).where(
                models.Budget.user_id == user_id,
                models.Budget.month == payload.month,
                models.Budget.category == category,
            )
        )

    record = _find()
    if record is None:
        record = models.Budget(
            id=str(uuid.uuid4()),
            user_id=user_id,
            month=payload.month,
            category=category,
            encrypted_payload=encrypt_json(key, {"amount_fen": payload.amount_fen}),
        )
        db.add(record)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            record = _find()
            if record is None:
                raise
            record.encrypted_payload = encrypt_json(key, {"amount_fen": payload.amount_fen})
            record.updated_at = utcnow()
            db.commit()
    else:
        record.encrypted_payload = encrypt_json(key, {"amount_fen": payload.amount_fen})
        record.updated_at = utcnow()
        db.commit()

    return Budget(
        id=record.id,
        month=record.month,
        category=ResolvedCategory(record.category),
        amount_fen=payload.amount_fen,
    )


def read_amount(db: Session, key: str, record: models.Budget) -> int | None:
    """只给测试与排查用：读回单条预算金额，密文坏了返回 None。"""
    try:
        return int(decrypt_json(key, record.encrypted_payload).get("amount_fen", 0))
    except (CryptoError, TypeError, ValueError):
        return None
