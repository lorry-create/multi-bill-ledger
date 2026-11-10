"""分类月预算。

契约只有 PUT，没有 GET：预算的读取跟着月报一起返回（`MonthlyReport.budgets`），
单独再开一个读接口会让前端拿到两个可能不同步的预算视图。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..contracts import Budget, BudgetInput, Error
from ..deps import AuthContext, get_db, require_csrf
from ..services import budgets as budget_service

router = APIRouter(prefix="/api/budgets", tags=["预算弹窗"])

_ERR = {"model": Error, "description": "统一错误结构"}


@router.put("", response_model=Budget, responses={401: _ERR, 403: _ERR, 422: _ERR})
def put_budget(
    payload: BudgetInput,
    request: Request,
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Budget:
    return budget_service.put_budget(
        db,
        request.app.state.settings.data_encryption_key,
        user_id=auth.user.id,
        payload=payload,
    )
