"""已确认账单、个人规则、预算和月报。"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..contracts import (Budget, BudgetInput, Category, ClassificationRule, Error, ErrorDetails,
    FlowType, MonthlyReport, ResolvedCategory, RuleList, RulePatch, Source,
    Transaction, TransactionPage, TransactionPatch)
from ..crypto import decrypt_json, encrypt_json
from ..deps import AuthContext, get_db, require_csrf, require_session
from ..errors import ApiError
from ..services.ledger import (SHANGHAI, month_of, remember_rule, require_owned, rule_view,
    transaction_digest, transaction_view)
from ..services.reporting import build_monthly_report

router = APIRouter(prefix="/api", tags=["ledger"])
_ERR = {"model": Error, "description": "统一错误结构"}


def filtered(db: Session, user_id: str, key: str, date_from: date | None = None,
             date_to: date | None = None, category: Category | None = None,
             source: Source | None = None, flow_type: FlowType | None = None) -> list[Transaction]:
    if date_from and date_to and date_from > date_to:
        raise ApiError("INVALID_DATE_RANGE", 422, "开始日期不能晚于结束日期")
    q = select(models.Transaction).where(models.Transaction.user_id == user_id,
        models.Transaction.status == "confirmed")
    if category: q = q.where(models.Transaction.category == category.value)
    if source: q = q.where(models.Transaction.source == source.value)
    if flow_type: q = q.where(models.Transaction.flow_type == flow_type.value)
    result = []
    for record in db.scalars(q):
        item = transaction_view(record, key)
        day = item.occurred_at.astimezone(SHANGHAI).date()
        if date_from and day < date_from: continue
        if date_to and day > date_to: continue
        result.append(item)
    result.sort(key=lambda x: (x.occurred_at, x.id), reverse=True)
    return result


@router.get("/transactions", response_model=TransactionPage, responses={401:_ERR,422:_ERR})
def list_transactions(request: Request, date_from: date | None = None,
        date_to: date | None = None, category: Category | None = None,
        source: Source | None = None, flow_type: FlowType | None = None,
        page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
        auth: AuthContext = Depends(require_session), db: Session = Depends(get_db)) -> TransactionPage:
    items = filtered(db, auth.user.id, request.app.state.settings.data_encryption_key,
                     date_from, date_to, category, source, flow_type)
    return TransactionPage(items=items[(page-1)*page_size:page*page_size],
                           total=len(items), page=page, page_size=page_size)


@router.patch("/transactions/{id}", response_model=Transaction,
              responses={401:_ERR,403:_ERR,404:_ERR,409:_ERR,422:_ERR})
def patch_transaction(id: str, patch: TransactionPatch, request: Request,
        auth: AuthContext = Depends(require_csrf), db: Session = Depends(get_db)) -> Transaction:
    row = require_owned(db, models.Transaction, id, auth.user.id)
    if row.version != patch.expected_version:
        raise ApiError("VERSION_CONFLICT", 409, "账单已更新，请刷新后重试",
                       ErrorDetails(current_version=row.version))
    key = request.app.state.settings.data_encryption_key
    old = decrypt_json(key, row.encrypted_payload)
    changes = patch.changes.model_dump(mode="json", exclude_unset=True)
    if any(v is None for k,v in changes.items() if k != "source_transaction_id"):
        raise ApiError("NULL_FIELD", 422, "该字段不能设为空")
    new = {**old, **changes}
    candidate = Transaction.model_validate({**new, "id": row.id, "version": row.version,
        "source": row.source, "import_batch_id": row.import_batch_id, "status":"confirmed"})
    if patch.remember_rule and (candidate.category == Category.pending or not candidate.merchant.strip()):
        raise ApiError("RULE_INPUT_INVALID", 422, "记住分类需要明确商户和类别")
    source_id = candidate.source_transaction_id
    digest = transaction_digest(key, auth.user.id, row.source, candidate.flow_type.value, source_id)
    if source_id and digest != row.dedupe_digest:
        collision = db.scalar(select(models.Transaction.id).where(
            models.Transaction.user_id == auth.user.id,
            models.Transaction.dedupe_digest == digest,
            models.Transaction.id != id))
        if collision: raise ApiError("DUPLICATE_TRANSACTION", 409, "修改后与已有交易重复")
    row.encrypted_payload = encrypt_json(key, new)
    row.month_index = month_of(candidate.occurred_at)
    row.category = candidate.category.value
    row.flow_type = candidate.flow_type.value
    row.dedupe_digest = digest
    row.version += 1
    rule_created = False
    if patch.remember_rule:
        rule_created = remember_rule(db, auth.user.id, row.source,
                                    candidate.merchant, candidate.category.value, key)
    db.add(models.CorrectionLog(id=str(uuid.uuid4()), user_id=auth.user.id,
        transaction_id=row.id, rule_created=rule_created,
        encrypted_payload=encrypt_json(key, {"before":old,"after":new})))
    db.commit()
    db.refresh(row)
    return transaction_view(row, key)


@router.get("/classification-rules", response_model=RuleList, responses={401:_ERR})
def list_rules(request: Request, auth: AuthContext = Depends(require_session),
               db: Session = Depends(get_db)) -> RuleList:
    key = request.app.state.settings.data_encryption_key
    rows = db.scalars(select(models.ClassificationRule).where(
        models.ClassificationRule.user_id == auth.user.id)).all()
    return RuleList(items=[rule_view(row,key) for row in rows])


@router.patch("/classification-rules/{id}", response_model=ClassificationRule,
              responses={401:_ERR,403:_ERR,404:_ERR,409:_ERR,422:_ERR})
def patch_rule(id: str, patch: RulePatch, request: Request,
        auth: AuthContext = Depends(require_csrf), db: Session = Depends(get_db)) -> ClassificationRule:
    row = require_owned(db, models.ClassificationRule, id, auth.user.id)
    if row.version != patch.expected_version:
        raise ApiError("VERSION_CONFLICT", 409, "规则已更新，请刷新后重试",
                       ErrorDetails(current_version=row.version))
    key = request.app.state.settings.data_encryption_key
    payload = decrypt_json(key, row.encrypted_payload)
    if patch.category is not None: payload["category"] = patch.category.value
    if patch.enabled is not None: row.enabled = patch.enabled
    row.encrypted_payload = encrypt_json(key, payload)
    row.version += 1
    db.commit()
    db.refresh(row)
    return rule_view(row,key)


@router.get("/reports/monthly", response_model=MonthlyReport, responses={401:_ERR,422:_ERR})
def monthly_report(request: Request, month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
        auth: AuthContext = Depends(require_session),
        db: Session = Depends(get_db)) -> MonthlyReport:
    return build_monthly_report(db, auth.user.id, month,
                                request.app.state.settings.data_encryption_key)


@router.put("/budgets", response_model=Budget, responses={401:_ERR,403:_ERR,422:_ERR})
def put_budget(payload: BudgetInput, request: Request,
        auth: AuthContext = Depends(require_csrf), db: Session = Depends(get_db)) -> Budget:
    row = db.scalar(select(models.Budget).where(models.Budget.user_id == auth.user.id,
        models.Budget.month == payload.month,
        models.Budget.category == payload.category.value))
    if row is None:
        row = models.Budget(id=str(uuid.uuid4()), user_id=auth.user.id,
                            month=payload.month, category=payload.category.value)
        db.add(row)
    row.encrypted_payload = encrypt_json(request.app.state.settings.data_encryption_key,
                                          {"amount_fen":payload.amount_fen})
    db.commit()
    return Budget(id=row.id, **payload.model_dump())
