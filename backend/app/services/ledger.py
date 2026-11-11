"""账单业务模型与加密存储之间的唯一转换层。"""
from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..contracts import Batch, ClassificationRule, Progress, Transaction, TransactionDraft
from ..crypto import decrypt_json, encrypt_json, dedupe_digest
from ..errors import ApiError
from ..intelligence.normalize import normalize_merchant

SHANGHAI = ZoneInfo("Asia/Shanghai")


def month_of(value: datetime | str) -> str:
    date = datetime.fromisoformat(value) if isinstance(value, str) else value
    if date.tzinfo is None:
        raise ApiError("TIMEZONE_REQUIRED", 422, "交易时间必须包含时区")
    return date.astimezone(SHANGHAI).strftime("%Y-%m")


def batch_view(row: models.ImportBatch, key: str) -> Batch:
    filename = decrypt_json(key, row.encrypted_filename)["filename"] if row.encrypted_filename else ""
    drafts = decrypt_json(key, row.encrypted_rows).get("rows", []) if row.encrypted_rows else []
    issues = decrypt_json(key, row.encrypted_issues).get("issues", []) if row.encrypted_issues else []
    return Batch(id=row.id, version=row.version, source=row.source,
                 ingestion_method=row.ingestion_method, status=row.status,
                 rows=[TransactionDraft.model_validate(x) for x in drafts], issues=issues,
                 progress=Progress(current=row.progress_current, total=row.progress_total),
                 file_name=filename, created_at=row.created_at, updated_at=row.updated_at)


def transaction_view(row: models.Transaction, key: str) -> Transaction:
    payload = decrypt_json(key, row.encrypted_payload)
    return Transaction.model_validate({**payload, "id": row.id, "version": row.version,
        "source": row.source, "import_batch_id": row.import_batch_id,
        "status": row.status})


def rule_view(row: models.ClassificationRule, key: str) -> ClassificationRule:
    payload = decrypt_json(key, row.encrypted_payload)
    return ClassificationRule.model_validate({"id": row.id, "version": row.version,
        "source": row.source, "enabled": row.enabled, **payload})


def user_rules(db: Session, user_id: str, source: str, key: str) -> list[ClassificationRule]:
    rows = db.scalars(select(models.ClassificationRule).where(
        models.ClassificationRule.user_id == user_id,
        models.ClassificationRule.source == source,
        models.ClassificationRule.enabled == True)).all()
    return [rule_view(x, key) for x in rows]


def remember_rule(db: Session, user_id: str, source: str, merchant: str, category: str, key: str) -> bool:
    normalized = normalize_merchant(merchant)
    if not normalized or category == "pending":
        raise ApiError("RULE_INPUT_INVALID", 422, "记住分类需要明确的商户和类别")
    rows = db.scalars(select(models.ClassificationRule).where(
        models.ClassificationRule.user_id == user_id,
        models.ClassificationRule.source == source)).all()
    for row in rows:
        if decrypt_json(key, row.encrypted_payload)["merchant_normalized"] == normalized:
            row.encrypted_payload = encrypt_json(key, {"merchant_normalized": normalized, "category": category})
            row.enabled = True
            row.version += 1
            return False
    db.add(models.ClassificationRule(id=str(uuid.uuid4()), user_id=user_id,
        source=source, enabled=True, version=1,
        encrypted_payload=encrypt_json(key, {"merchant_normalized": normalized, "category": category})))
    return True


def transaction_digest(key: str, user_id: str, source: str, flow: str, source_id: str | None) -> str:
    # 无可靠平台交易号时不自动合并；人工确认后使用随机事件标识。
    return dedupe_digest(key, user_id, source, flow, source_id or str(uuid.uuid4()))


def require_owned(db: Session, model, item_id: str, user_id: str):
    row = db.get(model, item_id)
    if row is None or row.user_id != user_id:
        raise ApiError("NOT_FOUND", 404, "记录不存在")
    return row
