"""与页面筛选和月报口径一致的导出。"""
from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..contracts import Category, Error, FlowType, Source
from ..deps import AuthContext, get_db, require_session
from ..errors import ApiError
from ..services.reporting import build_monthly_report
from .ledger import filtered

router = APIRouter(prefix="/api/exports", tags=["exports"])
_ERR = {"model": Error, "description": "统一错误结构"}


def safe_cell(value: str) -> str:
    # 防 CSV 公式注入；前导空白后的公式字符也需要拦截。
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


@router.get("/transactions.csv", responses={401:_ERR,422:_ERR,503:_ERR})
def export_transactions(request: Request, date_from: date | None = None,
        date_to: date | None = None, category: Category | None = None,
        source: Source | None = None, flow_type: FlowType | None = None,
        auth: AuthContext = Depends(require_session), db: Session = Depends(get_db)) -> Response:
    rows = filtered(db, auth.user.id, request.app.state.settings.data_encryption_key,
                    date_from, date_to, category, source, flow_type)
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(["交易时间", "平台", "方向", "商户", "说明", "类别", "金额(分)", "平台交易号"])
    for row in rows:
        writer.writerow([row.occurred_at.isoformat(), row.source.value, row.flow_type.value,
                         safe_cell(row.merchant), safe_cell(row.description),
                         row.category.value, row.amount_fen,
                         safe_cell(row.source_transaction_id or "")])
    return Response("\ufeff" + out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition":"attachment; filename=transactions.csv",
                             "Cache-Control":"no-store"})


@router.get("/monthly.pdf", responses={401:_ERR,422:_ERR,503:_ERR})
def export_monthly_pdf(request: Request,
        month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
        auth: AuthContext = Depends(require_session), db: Session = Depends(get_db)) -> Response:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise ApiError("PDF_UNAVAILABLE", 503, "PDF 导出组件尚未安装") from exc
    report = build_monthly_report(db, auth.user.id, month,
                                   request.app.state.settings.data_encryption_key)
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    out = io.BytesIO()
    page = canvas.Canvas(out, pagesize=A4)
    page.setTitle(f"归账 {month} 月报")
    page.setFont("STSong-Light", 20)
    page.drawString(48, 790, f"归账  {month} 月度收支报告")
    page.setFont("STSong-Light", 11)
    labels = [
        ("收入", report.totals.income_fen),
        ("毛支出", report.totals.gross_expense_fen),
        ("退款", report.totals.refund_fen),
        ("净支出", report.totals.net_expense_fen),
        ("收支差额", report.totals.balance_fen),
    ]
    y = 740
    for label, fen in labels:
        page.drawString(48, y, f"{label}：{fen / 100:.2f} 元")
        y -= 28
    page.drawString(48, y-15, "收支差额不代表账户余额。分类分布按毛支出统计。")
    y -= 64
    page.setFont("STSong-Light", 14)
    page.drawString(48, y, "支出类别")
    y -= 28
    page.setFont("STSong-Light", 10)
    names = {"dining":"餐饮", "transport":"交通", "shopping":"购物", "salary":"工资",
             "housing":"居住", "entertainment":"娱乐", "health":"医疗",
             "education":"教育", "other":"其他", "pending":"待确认"}
    gross = max(1, report.totals.gross_expense_fen)
    for item in report.expense_by_category:
        page.drawString(48, y, f"{names[item.category.value]}  {item.amount_fen / 100:.2f} 元")
        page.setFillColorRGB(.30, .33, .91)
        page.rect(275, y-3, 230*item.amount_fen/gross, 8, fill=1, stroke=0)
        page.setFillColorRGB(0, 0, 0)
        y -= 25
    y -= 23
    page.setFont("STSong-Light", 14)
    page.drawString(48, y, "每日收入 / 毛支出")
    y -= 140
    maximum = max(1, *(max(x.income_fen, x.gross_expense_fen) for x in report.daily_trend))
    width = 475 / max(1,len(report.daily_trend))
    for index, day in enumerate(report.daily_trend):
        x = 48 + index*width
        page.setFillColorRGB(.30, .33, .91)
        page.rect(x,y,width*.35,95*day.income_fen/maximum,fill=1,stroke=0)
        page.setFillColorRGB(.68,.71,.94)
        page.rect(x+width*.4,y,width*.35,95*day.gross_expense_fen/maximum,fill=1,stroke=0)
    page.setFillColorRGB(0,0,0)
    page.setFont("STSong-Light", 9)
    page.drawString(48, y-16, "蓝色：收入    浅蓝：毛支出")
    page.showPage()
    page.save()
    return Response(out.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition":f"attachment; filename=monthly-{month}.pdf",
                             "Cache-Control":"no-store"})
