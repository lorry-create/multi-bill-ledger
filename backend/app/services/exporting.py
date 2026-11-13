"""导出：账单 CSV 与月报 PDF。

两条契约硬要求（docs/11、contracts/openapi.json）：

1. **CSV 导出"所有筛选结果，不限当前分页"**，且必须"文本单元格防公式注入"。
   前者靠复用 `services.transactions.filtered_rows`（与列表页同一份筛选实现），
   后者是 OWASP 的 CSV Injection：以 `=` `+` `-` `@` 开头的单元格被 Excel 打开时
   会当公式执行，商户名里放一句 `=cmd|'/c calc'!A1` 就能在别人机器上跑命令。
   这里统一前置一个单引号，让 Excel 当纯文本。
2. **PDF 必须与同月月报数字相同**。所以数字只从
   `services.reporting.build_monthly_report` 来，本文件**不重新汇总**。
   字体或渲染依赖缺失时返回 503 `EXPORT_UNAVAILABLE`（契约已声明这个分支），
   绝不输出一份中文全是方块、数字还可能是错的 PDF 冒充成功。

字体说明：reportlab 只能嵌入 TrueType 轮廓的字体，Noto CJK 那类 CFF/OTF
加载会失败。所以容器里装的是文泉驿（wqy-zenhei，TrueType），见 backend/Dockerfile。
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from ..contracts import ErrorDetails
from ..errors import ApiError
from . import reporting
from .transactions import filtered_rows

logger = logging.getLogger("app.services.exporting")

SHANGHAI = ZoneInfo("Asia/Shanghai")

# 契约示例列（source, amount_fen, flow_type, category）都在里面，另加时间与说明，
# 方便用户拿去自己做透视表
CSV_COLUMNS = (
    "occurred_at",
    "source",
    "flow_type",
    "category",
    "amount_fen",
    "currency",
    "merchant",
    "description",
    "classification_source",
    "source_transaction_id",
)

# Excel 视这些开头为公式（含制表符与回车：老漏洞会用它把内容推进下一个单元格）
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

# PDF 是给中文用户看的，不能直接印 dining / transport 这种内部代码。
# 只影响显示，接口返回的枚举值不变。
CATEGORY_LABELS = {
    "dining": "餐饮",
    "transport": "交通",
    "shopping": "购物",
    "salary": "工资",
    "housing": "居住",
    "entertainment": "娱乐",
    "health": "医疗",
    "education": "教育",
    "other": "其他",
    "pending": "待分类",
}


def category_label(value: object) -> str:
    code = getattr(value, "value", value)
    return CATEGORY_LABELS.get(str(code), str(code))


def _safe_text(value: object) -> str:
    """文本单元格防公式注入。只在首字符命中时加单引号，不影响正常内容。"""
    text = "" if value is None else str(value)
    if text and text[0] in _FORMULA_PREFIXES:
        return "'" + text
    return text


def _yuan(fen: object) -> str:
    try:
        return f"{int(fen) / 100:.2f}"
    except (TypeError, ValueError):
        return "0.00"


def build_transactions_csv(
    db: Session,
    user_id: str,
    key: str,
    *,
    date_from=None,
    date_to=None,
    category=None,
    source=None,
    flow_type=None,
    max_rows: int = 50000,
) -> tuple[bytes, str]:
    """返回 (CSV 字节, 建议文件名)。行数超限报 422 而不是悄悄截断。"""
    rows = filtered_rows(
        db,
        user_id,
        key,
        date_from=date_from,
        date_to=date_to,
        category=category,
        source=source,
        flow_type=flow_type,
    )

    if len(rows) > max_rows:
        raise ApiError(
            "VALIDATION_ERROR",
            422,
            f"筛选结果 {len(rows)} 行，超过单次导出上限 {max_rows} 行，请缩小日期范围",
            ErrorDetails(),
        )

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for record, payload, _occurred in rows:
        writer.writerow(
            [
                _safe_text(payload.get("occurred_at")),
                _safe_text(getattr(payload.get("source"), "value", record.source)),
                _safe_text(getattr(payload.get("flow_type"), "value", record.flow_type)),
                _safe_text(getattr(payload.get("category"), "value", record.category)),
                # 金额是整数分，不是文本，不能加单引号也不能被当成公式
                int(payload.get("amount_fen") or 0),
                _safe_text(payload.get("currency") or "CNY"),
                _safe_text(payload.get("merchant")),
                _safe_text(payload.get("description")),
                _safe_text(payload.get("classification_source")),
                _safe_text(payload.get("source_transaction_id")),
            ]
        )

    # UTF-8 **带 BOM**：不加 BOM 时 Excel 双击打开中文商户名会乱码。
    # 程序化解析请用 utf-8-sig 解码（docs/11 已注明）。
    data = buffer.getvalue().encode("utf-8-sig")

    if date_from or date_to:
        span = f"{date_from or '起始'}_{date_to or '至今'}"
    else:
        span = datetime.now(SHANGHAI).strftime("%Y%m%d")
    return data, f"账单导出_{span}.csv"


# ---------------------------------------------------------------- PDF

# reportlab 只认 TrueType 轮廓；.ttc 需要 subfontIndex。顺序即优先级：
# 优先单文件 TTF（最稳），容器里的文泉驿其次。
_FONT_CANDIDATES: tuple[tuple[str, str, int | None], ...] = (
    ("CJK-simhei", "C:/Windows/Fonts/simhei.ttf", None),
    ("CJK-deng", "C:/Windows/Fonts/Deng.ttf", None),
    ("CJK-msyh", "C:/Windows/Fonts/msyh.ttc", 0),
    ("CJK-simsun", "C:/Windows/Fonts/simsun.ttc", 0),
    ("CJK-wqy-zenhei", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0),
    ("CJK-wqy-microhei", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0),
    ("CJK-arphic", "/usr/share/fonts/truetype/arphic/uming.ttc", 0),
    ("CJK-droid", "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf", None),
)

_font_state: dict[str, str | None] = {"key": None, "name": None}


def _unavailable(detail: str) -> ApiError:
    logger.warning("月报 PDF 不可用：%s", detail)
    return ApiError(
        "EXPORT_UNAVAILABLE",
        503,
        "报表导出暂不可用，请稍后重试",
        ErrorDetails(),
    )


def _resolve_font(explicit_path: str = "") -> str:
    """注册并返回可用的中文字体名；找不到就抛 503，不返回 None 让上层踩空。"""
    if _font_state["name"] and _font_state["key"] == explicit_path:
        return _font_state["name"]

    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        raise _unavailable("reportlab 未安装") from None

    candidates = list(_FONT_CANDIDATES)
    if explicit_path:
        # 显式配置优先，且 .ttc 时尝试子字体 0
        suffix = Path(explicit_path).suffix.lower()
        candidates.insert(0, ("CJK-config", explicit_path, 0 if suffix == ".ttc" else None))

    for name, path, index in candidates:
        if not Path(path).exists():
            continue
        try:
            font = TTFont(name, path, subfontIndex=index) if index is not None else TTFont(name, path)
            pdfmetrics.registerFont(font)
        except Exception as exc:  # noqa: BLE001 - 字体文件千奇百怪，统一降级
            logger.info("字体 %s 加载失败：%s", path, exc)
            continue
        _font_state["key"] = explicit_path
        _font_state["name"] = name
        return name

    raise _unavailable("找不到可嵌入的中文字体，请设置 PDF_FONT_PATH")


def build_monthly_pdf(
    db: Session,
    user_id: str,
    month: str,
    key: str,
    font_path: str = "",
) -> tuple[bytes, str]:
    """返回 (PDF 字节, 建议文件名)。数字全部来自 build_monthly_report。"""
    font = _resolve_font(font_path)

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except ImportError:
        raise _unavailable("reportlab 未安装") from None

    report = reporting.build_monthly_report(db, user_id, month, key)
    totals = report.totals
    year, mon = month.split("-")

    buffer = io.BytesIO()
    page_w, page_h = A4
    margin = 18 * mm
    width = page_w - margin * 2
    bottom_guard = margin + 16 * mm

    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f"{year} 年 {int(mon)} 月收支月报")
    c.setAuthor("multi-bill-ledger")
    y = page_h - margin
    page_num = 1

    def start_new_page() -> None:
        nonlocal y, page_num
        c.showPage()
        page_num += 1
        y = page_h - margin
        c.setFont(font, 9)
        c.setFillColorRGB(0.45, 0.45, 0.45)
        c.drawString(margin, y, f"{year} 年 {int(mon)} 月收支月报（第 {page_num} 页）")
        y -= 4 * mm
        c.setStrokeColorRGB(0.88, 0.88, 0.88)
        c.setLineWidth(0.5)
        c.line(margin, y, margin + width, y)
        y -= 7 * mm

    def ensure_space(need: float, after_break=None) -> None:
        if y - need < bottom_guard:
            start_new_page()
            if after_break is not None:
                after_break()

    # ---- 标题
    c.setFont(font, 20)
    c.setFillColorRGB(0.05, 0.05, 0.05)
    c.drawString(margin, y, f"{year} 年 {int(mon)} 月收支月报")
    y -= 7 * mm
    c.setFont(font, 9)
    c.setFillColorRGB(0.45, 0.45, 0.45)
    c.drawString(margin, y, f"统计月份 {month}　金额单位：元")
    y -= 8 * mm

    c.setStrokeColorRGB(0.85, 0.85, 0.85)
    c.setLineWidth(0.5)
    c.line(margin, y, margin + width, y)
    y -= 7 * mm

    # ---- 合计
    c.setFont(font, 11)
    c.setFillColorRGB(0.05, 0.05, 0.05)
    c.drawString(margin, y, "收支合计")
    y -= 6.5 * mm

    summary = (
        ("收入", _yuan(totals.income_fen)),
        ("毛支出", _yuan(totals.gross_expense_fen)),
        ("退款", _yuan(totals.refund_fen)),
        ("净支出", _yuan(totals.net_expense_fen)),
        ("收支差额", _yuan(totals.balance_fen)),
    )
    col_w = width / 2
    for index, (label, value) in enumerate(summary):
        row, col = divmod(index, 2)
        x = margin + col * col_w
        line_y = y - row * 6 * mm
        c.setFont(font, 9)
        c.setFillColorRGB(0.45, 0.45, 0.45)
        c.drawString(x, line_y, label)
        c.setFont(font, 11)
        c.setFillColorRGB(0.05, 0.05, 0.05)
        c.drawString(x + 24 * mm, line_y, value)
    y -= (len(summary) + 1) // 2 * 6 * mm + 5 * mm

    # ---- 分类构成（含横向条形，满足任务书"可视化"要求）
    ensure_space(16 * mm)
    c.setFont(font, 11)
    c.setFillColorRGB(0.05, 0.05, 0.05)
    c.drawString(margin, y, "支出分类构成")
    y -= 6.5 * mm

    items = report.expense_by_category
    if not items:
        c.setFont(font, 9)
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.drawString(margin, y, "本月无支出记录")
        y -= 7 * mm
    else:
        biggest = max(item.amount_fen for item in items) or 1
        bar_x = margin + 26 * mm
        bar_max = width - 26 * mm - 22 * mm
        for item in items:
            ensure_space(7 * mm)
            c.setFont(font, 9)
            c.setFillColorRGB(0.25, 0.25, 0.25)
            c.drawString(margin, y, category_label(item.category))
            c.setFillColorRGB(0.35, 0.55, 0.75)
            bar_w = max(1.0, bar_max * item.amount_fen / biggest)
            c.rect(bar_x, y - 1, bar_w, 4.5 * mm, stroke=0, fill=1)
            c.setFillColorRGB(0.15, 0.15, 0.15)
            c.drawRightString(margin + width, y, _yuan(item.amount_fen))
            y -= 6 * mm
        y -= 2 * mm

    # ---- 日支出趋势（任务书要求报表含支出趋势；空白天不列，免得刷 30 行 0）
    active_days = [
        point
        for point in report.daily_trend
        if point.income_fen or point.gross_expense_fen or point.refund_fen
    ]
    if active_days:
        columns = (
            ("日期", margin),
            ("收入", margin + 30 * mm),
            ("毛支出", margin + 55 * mm),
            ("退款", margin + 80 * mm),
            ("净支出", margin + 103 * mm),
        )

        def draw_trend_header(cont: bool = False) -> None:
            nonlocal y
            c.setFont(font, 11)
            c.setFillColorRGB(0.05, 0.05, 0.05)
            c.drawString(margin, y, "每日支出趋势（续）" if cont else "每日支出趋势")
            y -= 6 * mm
            c.setFont(font, 8.5)
            c.setFillColorRGB(0.45, 0.45, 0.45)
            for label, x in columns:
                c.drawString(x, y, label)
            y -= 4.6 * mm

        ensure_space(18 * mm)
        draw_trend_header(False)

        for point in active_days:
            ensure_space(5.5 * mm, lambda: draw_trend_header(True))
            c.setFont(font, 8.5)
            c.setFillColorRGB(0.25, 0.25, 0.25)
            c.drawString(margin, y, point.date.isoformat())
            c.setFillColorRGB(0.15, 0.15, 0.15)
            for value, (_label, x) in zip(
                (
                    point.income_fen,
                    point.gross_expense_fen,
                    point.refund_fen,
                    point.net_expense_fen,
                ),
                columns[1:],
            ):
                c.drawString(x, y, _yuan(value))
            y -= 4.6 * mm
        y -= 2 * mm

    # ---- 预算执行
    if report.budgets:
        def draw_budget_header(cont: bool = False) -> None:
            nonlocal y
            c.setFont(font, 11)
            c.setFillColorRGB(0.05, 0.05, 0.05)
            c.drawString(margin, y, "预算执行（续）" if cont else "预算执行")
            y -= 6.5 * mm

        ensure_space(15 * mm)
        draw_budget_header(False)
        for status in report.budgets:
            ensure_space(6.5 * mm, lambda: draw_budget_header(True))
            c.setFont(font, 9)
            c.setFillColorRGB(0.25, 0.25, 0.25)
            c.drawString(margin, y, category_label(status.category))
            c.setFillColorRGB(0.15, 0.15, 0.15)
            over = _yuan(status.over_fen)
            text = (
                f"预算 {_yuan(status.budget_fen)}　已用 {_yuan(status.spent_fen)}"
                f"　剩余 {_yuan(status.remaining_fen)}　超出 {over}"
            )
            c.drawString(margin + 26 * mm, y, text)
            y -= 6 * mm
        y -= 2 * mm

    # ---- 脚注：空间不足时换页再写，绝不盖住前面的列表或预算数据
    if y < margin + 18 * mm:
        start_new_page()
    y = min(y, margin + 16 * mm)
    c.setStrokeColorRGB(0.88, 0.88, 0.88)
    c.line(margin, y, margin + width, y)
    y -= 5 * mm
    c.setFont(font, 8)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawString(margin, y, "净支出 = 毛支出 - 退款；收支差额 = 收入 - 净支出。与接口月报同口径。")
    y -= 4.5 * mm
    c.drawString(
        margin,
        y,
        "预算的已用金额按净支出计算，某类只发生退款时可为负数。",
    )
    y -= 4.5 * mm
    c.drawString(
        margin,
        y,
        f"生成时间 {datetime.now(SHANGHAI).strftime('%Y-%m-%d %H:%M')}（Asia/Shanghai）",
    )

    c.showPage()
    c.save()
    return buffer.getvalue(), f"收支月报_{month}.pdf"


__all__ = [
    "CSV_COLUMNS",
    "build_monthly_pdf",
    "build_transactions_csv",
]
