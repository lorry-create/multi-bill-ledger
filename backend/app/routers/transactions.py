"""账单列表与纠错。

字段全部来自契约 `listTransactions` / `patchTransaction`，不自己加字段：
前端按 `contracts/openapi.json` 生成的类型写页面，这里多一个少一个都会对不上。

两个易错点写在这里，省得以后翻代码：
- 日期参数是**上海自然日**且两端包含，转换与比较统一交给 `services.dedupe.day_key`；
- 写接口用 `require_csrf`，读接口用 `require_session`，与其余模块保持一致。
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..contracts import (
    Category,
    Error,
    FlowType,
    Source,
    Transaction,
    TransactionPage,
    TransactionPatch,
)
from ..deps import AuthContext, get_db, require_csrf, require_session
from ..services import transactions as txn_service

router = APIRouter(prefix="/api/transactions", tags=["账单页"])

# 非 2xx 一律是统一 Error 结构。不显式声明，生成的 SDK 里就没有这些错误分支，
# 前端只能按 status code 猜——那等于契约白写。
_ERR = {"model": Error, "description": "统一错误结构"}


@router.get("", response_model=TransactionPage, responses={401: _ERR, 422: _ERR})
def list_transactions(
    request: Request,
    date_from: date | None = Query(default=None, description="包含该上海自然日"),
    date_to: date | None = Query(default=None, description="包含该上海自然日"),
    category: Category | None = Query(default=None),
    source: Source | None = Query(default=None),
    flow_type: FlowType | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    auth: AuthContext = Depends(require_session),
    db: Session = Depends(get_db),
) -> TransactionPage:
    return txn_service.list_transactions(
        db,
        auth.user.id,
        request.app.state.settings.data_encryption_key,
        date_from=date_from,
        date_to=date_to,
        category=category,
        source=source,
        flow_type=flow_type,
        page=page,
        page_size=page_size,
    )


@router.patch(
    "/{id}",
    response_model=Transaction,
    responses={401: _ERR, 403: _ERR, 404: _ERR, 409: _ERR, 422: _ERR},
)
def patch_transaction(
    id: str,
    payload: TransactionPatch,
    request: Request,
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Transaction:
    return txn_service.patch_transaction(
        db,
        request.app.state.settings.data_encryption_key,
        user_id=auth.user.id,
        transaction_id=id,
        patch=payload,
    )
