"""月度报表。

这里**不计算任何数字**，只把 `services/reporting.build_monthly_report` 的结果
原样返回。列表、图表、导出共用同一口径是 A10 的硬要求，多一层计算就多一处
可能不一致的地方。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..contracts import Error, MonthlyReport
from ..deps import AuthContext, get_db, require_session
from ..services import reporting

router = APIRouter(prefix="/api/reports", tags=["月报页"])

_MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"

_ERR = {"model": Error, "description": "统一错误结构"}


@router.get("/monthly", response_model=MonthlyReport, responses={401: _ERR, 422: _ERR})
def get_monthly_report(
    request: Request,
    month: str = Query(pattern=_MONTH_PATTERN, description="YYYY-MM，必填，不静默默认当月"),
    auth: AuthContext = Depends(require_session),
    db: Session = Depends(get_db),
) -> MonthlyReport:
    return reporting.build_monthly_report(
        db,
        auth.user.id,
        month,
        request.app.state.settings.data_encryption_key,
    )
