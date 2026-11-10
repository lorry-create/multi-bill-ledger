"""导出：账单 CSV 与月报 PDF。

两条都是**二进制流**，不是 JSON。所以这里对每个响应显式声明 content-type：
不声明的话 FastAPI 会按 `application/json` 写进 OpenAPI，生成的 SDK 类型就是错的，
`tools/check_implemented_contract.py` 也会判字段不一致。
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from ..contracts import Category, Error, FlowType, Source
from ..deps import AuthContext, get_db, require_session
from ..http_utils import content_disposition
from ..services import exporting

router = APIRouter(prefix="/api/exports", tags=["账单页"])

_ERR = {"model": Error, "description": "统一错误结构"}

_MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"

_CSV_OK = {
    "description": "CSV 文件流（UTF-8 带 BOM，便于 Excel 直接打开）",
    "content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}},
}

_PDF_OK = {
    "description": "PDF 文件流（中文内嵌字体）",
    "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
}


@router.get(
    "/transactions.csv",
    response_class=Response,
    responses={200: _CSV_OK, 401: _ERR, 422: _ERR, 503: _ERR},
)
def export_transactions(
    request: Request,
    date_from: date | None = Query(None, description="包含该上海自然日"),
    date_to: date | None = Query(None, description="包含该上海自然日，按下一日零点开区间计算"),
    category: Category | None = Query(None),
    source: Source | None = Query(None),
    flow_type: FlowType | None = Query(None),
    auth: AuthContext = Depends(require_session),
    db: Session = Depends(get_db),
) -> Response:
    settings = request.app.state.settings
    data, filename = exporting.build_transactions_csv(
        db,
        auth.user.id,
        settings.data_encryption_key,
        date_from=date_from,
        date_to=date_to,
        category=category,
        source=source,
        flow_type=flow_type,
        max_rows=settings.export_max_rows,
    )
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.get(
    "/monthly.pdf",
    response_class=Response,
    responses={200: _PDF_OK, 401: _ERR, 422: _ERR, 503: _ERR},
)
def export_monthly_pdf(
    request: Request,
    month: str = Query(pattern=_MONTH_PATTERN, description="YYYY-MM，必填"),
    auth: AuthContext = Depends(require_session),
    db: Session = Depends(get_db),
) -> Response:
    settings = request.app.state.settings
    data, filename = exporting.build_monthly_pdf(
        db,
        auth.user.id,
        month,
        settings.data_encryption_key,
        font_path=settings.pdf_font_path,
    )
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition(filename)},
    )
