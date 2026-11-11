"""文件采集、草稿核对与幂等确认。"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..contracts import (Batch, ConfirmInput, ConfirmResult, Error, ErrorDetails, FieldError,
                         IngestionMethod, Issue, RetryInput, Source, TransactionDraft)
from ..crypto import decrypt_bytes, decrypt_json, dedupe_digest, encrypt_bytes, encrypt_json
from ..db import utcnow
from ..deps import AuthContext, get_db, require_csrf, require_session
from ..errors import ApiError
from ..intelligence.base import IntelligenceFailure
from ..intelligence.factory import build_intelligence
from ..services.ledger import batch_view, month_of, require_owned, transaction_digest, user_rules

router = APIRouter(prefix="/api/imports", tags=["imports"])
_ERR = {"model": Error, "description": "统一错误结构"}


def _process(request: Request, db: Session, row: models.ImportBatch, raw: bytes) -> None:
    key = request.app.state.settings.data_encryption_key
    provider = build_intelligence(request.app.state.settings.intelligence_provider)
    try:
        filename = decrypt_json(key, row.encrypted_filename)["filename"]
        parsed = (provider.parse_bill_file(raw, filename, row.source) if row.ingestion_method == "file"
                  else provider.recognize_bill_image(raw, "image/png", row.source))
        drafts = parsed.rows
        classified = provider.classify_transactions(drafts, user_rules(db, row.user_id, row.source, key))
        by_id = {result.row_id: result for result in classified}
        for draft in drafts:
            result = by_id.get(draft.row_id)
            if result:
                draft.category = result.category
                draft.classification_source = result.classification_source
                draft.classification_reason = result.classification_reason
                draft.issues.extend(result.issues)
            if draft.source_transaction_id and draft.flow_type:
                digest = transaction_digest(key, row.user_id, row.source,
                                            draft.flow_type.value, draft.source_transaction_id)
                existing = db.scalar(select(models.Transaction.id).where(
                    models.Transaction.user_id == row.user_id,
                    models.Transaction.dedupe_digest == digest))
                if existing:
                    draft.duplicate_status = "duplicate"
            elif draft.duplicate_status == "unique":
                draft.duplicate_status = "suspected"
        row.encrypted_rows = encrypt_json(key, {"rows": [x.model_dump(mode="json") for x in drafts]})
        row.encrypted_issues = encrypt_json(key, {"issues": [x.model_dump(mode="json") for x in parsed.issues]})
        row.progress_current = row.progress_total = len(drafts)
        row.status = "pending_review"
    except IntelligenceFailure as exc:
        row.status = "failed"
        row.encrypted_issues = encrypt_json(key, {"issues": [Issue(
            row_id=None, field=None, code=exc.code, message=exc.message).model_dump(mode="json")]})
    row.version += 1
    row.updated_at = utcnow()


@router.post("", response_model=Batch, status_code=202,
             responses={401:_ERR,403:_ERR,413:_ERR,415:_ERR,422:_ERR})
async def create_import(request: Request, source: Source = Form(...),
                        ingestion_method: IngestionMethod = Form(...),
                        file: UploadFile = File(...),
                        auth: AuthContext = Depends(require_csrf), db: Session = Depends(get_db)) -> Batch:
    name = (file.filename or "upload")[:255]
    suffix = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    image = ingestion_method == IngestionMethod.screenshot
    if suffix not in (("png", "jpg", "jpeg") if image else ("csv", "xlsx")):
        raise ApiError("UNSUPPORTED_FILE", 415, "仅支持 CSV、XLSX、PNG 或 JPEG")
    raw = await file.read((5 if image else 10) * 1024 * 1024 + 1)
    if len(raw) > (5 if image else 10) * 1024 * 1024:
        raise ApiError("FILE_TOO_LARGE", 413, "文件超过大小限制")
    if not raw:
        raise ApiError("EMPTY_FILE", 422, "文件为空")
    key = request.app.state.settings.data_encryption_key
    row = models.ImportBatch(id=str(uuid.uuid4()), user_id=auth.user.id,
        source=source.value, ingestion_method=ingestion_method.value, status="processing",
        version=1, progress_current=0, progress_total=0, started_at=utcnow(),
        encrypted_filename=encrypt_json(key, {"filename": name}),
        encrypted_original=encrypt_bytes(key, raw))
    db.add(row)
    _process(request, db, row, raw)
    db.commit()
    db.refresh(row)
    return batch_view(row, key)


@router.get("/{id}", response_model=Batch, responses={401:_ERR,404:_ERR,422:_ERR})
def get_import(id: str, request: Request, auth: AuthContext = Depends(require_session),
               db: Session = Depends(get_db)) -> Batch:
    return batch_view(require_owned(db, models.ImportBatch, id, auth.user.id),
                      request.app.state.settings.data_encryption_key)


@router.get("/{id}/original", responses={401:_ERR,404:_ERR,422:_ERR,503:_ERR})
def get_import_original(id: str, request: Request,
        auth: AuthContext = Depends(require_session), db: Session = Depends(get_db)) -> Response:
    row = require_owned(db, models.ImportBatch, id, auth.user.id)
    if not row.encrypted_original:
        raise ApiError("ORIGINAL_UNAVAILABLE", 503, "原始文件不可用")
    key = request.app.state.settings.data_encryption_key
    name = decrypt_json(key, row.encrypted_filename)["filename"]
    mime = "image/png" if name.lower().endswith(".png") else "image/jpeg" if name.lower().endswith((".jpg", ".jpeg")) else "application/octet-stream"
    return Response(decrypt_bytes(key, row.encrypted_original), media_type=mime,
                    headers={"Cache-Control": "no-store"})


@router.post("/{id}/retry", response_model=Batch, status_code=202,
             responses={401:_ERR,403:_ERR,404:_ERR,409:_ERR,422:_ERR})
def retry_import(id: str, payload: RetryInput, request: Request,
        auth: AuthContext = Depends(require_csrf), db: Session = Depends(get_db)) -> Batch:
    row = require_owned(db, models.ImportBatch, id, auth.user.id)
    if row.version != payload.expected_version or row.status != "failed":
        raise ApiError("BATCH_CONFLICT", 409, "批次状态已变化", ErrorDetails(current_version=row.version))
    key = request.app.state.settings.data_encryption_key
    _process(request, db, row, decrypt_bytes(key, row.encrypted_original))
    db.commit()
    db.refresh(row)
    return batch_view(row, key)


@router.post("/{id}/confirm", response_model=ConfirmResult,
             responses={401:_ERR,403:_ERR,404:_ERR,409:_ERR,422:_ERR})
def confirm_import(id: str, payload: ConfirmInput, request: Request,
        auth: AuthContext = Depends(require_csrf), db: Session = Depends(get_db)) -> ConfirmResult:
    row = require_owned(db, models.ImportBatch, id, auth.user.id)
    key = request.app.state.settings.data_encryption_key
    body = payload.model_dump(mode="json")
    body_digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    if row.confirmation_request_id == payload.request_id:
        if row.request_body_digest != body_digest:
            raise ApiError("IDEMPOTENCY_CONFLICT", 409, "同一请求 ID 的内容已改变")
        return ConfirmResult.model_validate(decrypt_json(key, row.encrypted_confirm_result))
    if row.status != "pending_review" or row.version != payload.expected_version:
        raise ApiError("BATCH_CONFLICT", 409, "批次已更新，请重新核对", ErrorDetails(current_version=row.version))
    drafts = {x.row_id: x for x in batch_view(row, key).rows}
    ids = [x.row_id for x in payload.rows]
    if len(set(ids)) != len(ids) or set(ids) - drafts.keys():
        raise ApiError("UNKNOWN_ROW", 422, "确认行不属于该批次")
    created, duplicates = [], 0
    seen_digests: set[str] = set()
    for item in payload.rows:
        draft = drafts[item.row_id]
        if draft.duplicate_status == "suspected" and not item.allow_suspected_duplicate:
            raise ApiError("SUSPECTED_DUPLICATE", 422, "疑似重复交易须明确确认")
        tx = item.transaction
        stable = bool(tx.source_transaction_id)
        digest = transaction_digest(key, auth.user.id, row.source, tx.flow_type.value, tx.source_transaction_id)
        if draft.duplicate_status == "duplicate" or (stable and digest in seen_digests) or (stable and db.scalar(select(models.Transaction.id).where(
                models.Transaction.user_id == auth.user.id, models.Transaction.dedupe_digest == digest))):
            duplicates += 1
            continue
        if stable:
            seen_digests.add(digest)
        tx_data = tx.model_dump(mode="json")
        tx_data.update(ingestion_method=row.ingestion_method,
            classification_source=(draft.classification_source.value if tx.category == draft.category else "manual"),
            classification_reason=(draft.classification_reason if tx.category == draft.category else "用户确认时修正"))
        record = models.Transaction(id=str(uuid.uuid4()), user_id=auth.user.id,
            import_batch_id=row.id, source=row.source, flow_type=tx.flow_type.value,
            category=tx.category.value, status="confirmed", month_index=month_of(tx.occurred_at),
            dedupe_digest=digest, encrypted_payload=encrypt_json(key, tx_data))
        db.add(record)
        created.append(record.id)
    result = ConfirmResult(batch_id=row.id, created_count=len(created), duplicate_count=duplicates,
                           ignored_count=len(drafts)-len(payload.rows), transaction_ids=created)
    row.status = "completed"
    row.version += 1
    row.confirmation_request_id = payload.request_id
    row.request_body_digest = body_digest
    row.encrypted_confirm_result = encrypt_json(key, result.model_dump(mode="json"))
    db.commit()
    return result
