"""把上传的字节读成二维表。

平台导出的"CSV"并不规范，三层坑都要在这里处理掉，否则后面的字段映射全部落空：

1. **编码**：支付宝 PC 端历史上导出 GBK，新版是 UTF-8；微信是带 BOM 的 UTF-8。
   解错编码不会报错，只会让中文列名变成乱码，然后"表头找不到"。所以按
   utf-8-sig → gb18030 顺序试，gb18030 覆盖 GBK/GB2312。
2. **表头位置**：两个平台都在前若干行塞说明文字（账号、导出时间、汇总、
   分隔线），表头在第 5～17 行不等。所以不能按固定行号取，要扫描找。
3. **尾部垃圾**：导出文件末尾有"以上是全部记录"之类的说明行，列数不足，
   必须当结构行跳过而不是当坏行报错。
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from .base import INVALID_FILE, UNSUPPORTED_TEMPLATE, IntelligenceFailure

_MAX_HEADER_SCAN = 40  # 表头一定在前 40 行内；再多就是文件不对

SUPPORTED_SUFFIXES = (".csv", ".txt", ".xlsx", ".xls")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")


@dataclass(frozen=True)
class Table:
    header: list[str]
    rows: list[list[str]]
    header_line: int  # 表头在原文件中的 1-based 行号，报错时用来定位


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise IntelligenceFailure(INVALID_FILE, "文件编码无法识别，请重新导出为 CSV")


def _from_csv(data: bytes) -> list[list[str]]:
    text = _decode(data)
    # 支付宝导出用 \r\n 且个别字段含未转义引号，csv 默认能处理；不让异常中断整表
    reader = csv.reader(io.StringIO(text, newline=""))
    return [[cell.strip() for cell in row] for row in reader]


def _from_xlsx(data: bytes) -> list[list[str]]:
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - 环境缺库时才走这里
        raise IntelligenceFailure(
            UNSUPPORTED_TEMPLATE, "服务端未启用 Excel 解析，请另存为 CSV 后重新上传"
        ) from exc
    try:
        book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        raise IntelligenceFailure(INVALID_FILE, "Excel 文件无法打开") from exc
    sheet = book.active
    rows: list[list[str]] = []
    for row in sheet.iter_rows(values_only=True):
        rows.append(["" if cell is None else str(cell).strip() for cell in row])
    book.close()
    return rows


def load_table(data: bytes, filename: str) -> list[list[str]]:
    """按扩展名读出二维表。只负责"读"，不判断是什么平台的账单。"""
    if not data:
        raise IntelligenceFailure(INVALID_FILE, "文件为空")
    lower = filename.lower()
    if lower.endswith((".xlsx", ".xls")):
        if lower.endswith(".xls"):
            # xls 是老的 OLE 格式，openpyxl 打不开；不假装支持
            raise IntelligenceFailure(
                UNSUPPORTED_TEMPLATE, "暂不支持旧版 .xls，请另存为 .xlsx 或 CSV"
            )
        return _from_xlsx(data)
    if lower.endswith((".csv", ".txt")):
        return _from_csv(data)
    raise IntelligenceFailure(
        UNSUPPORTED_TEMPLATE, f"不支持的文件类型：{lower.rsplit('.', 1)[-1] or '未知'}"
    )


def find_header(rows: list[list[str]], must_contain: tuple[str, ...]) -> Table:
    """扫描定位表头行，返回表头之后的数据行。

    must_contain 里每个词都必须出现在同一行才算命中，避免把说明行的
    「交易时间：2026-10-01」误认成表头。
    """
    for index, row in enumerate(rows[:_MAX_HEADER_SCAN]):
        joined = ",".join(row)
        if all(word in joined for word in must_contain):
            body = _strip_tail(rows[index + 1 :])
            return Table(header=row, rows=body, header_line=index + 1)
    raise IntelligenceFailure(UNSUPPORTED_TEMPLATE)


def _strip_tail(rows: list[list[str]]) -> list[list[str]]:
    """去掉空行与说明行。

    判据是"非空单元格数 ≤ 1"，而不是"列数不足"：微信导出被 CSV 用逗号补齐到
    与表头等宽（`------以上是全部记录------,,,,,,,,,,`），列数完全达标，
    按列数判断会把它当成一条金额缺失的坏交易。
    合法交易至少同时有时间和金额两个非空单元格。
    """
    kept: list[list[str]] = []
    for row in rows:
        non_empty = sum(1 for cell in row if cell.strip())
        if non_empty <= 1:
            continue
        kept.append(row)
    return kept


def index_of(header: list[str], *candidates: str) -> int | None:
    """按候选名找列下标，忽略空白与全半角括号差异。

    支付宝的列名带全角括号（「金额（元）」），不同版本还可能在括号前加空格，
    所以比较前统一去空白、把（）换成()。
    """
    normalized = [_norm_name(cell) for cell in header]
    for candidate in candidates:
        target = _norm_name(candidate)
        if target in normalized:
            return normalized.index(target)
    return None


def _norm_name(raw: str) -> str:
    return raw.replace("（", "(").replace("）", ")").replace(" ", "").strip()
