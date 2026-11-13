"""离线截图 OCR 与账单字段提取（T06）。

设计纪律（docs/02、docs/05、docs/13、docs/20）：
1. 本地通过 RapidOCR (ONNX Runtime) 离线提字，不依赖外部收费 OCR 服务即可运行。
2. 既支持单笔「账单详情」截图，也支持多行「账单列表」截图。
3. 严禁猜字段：截图时间缺年份（如 `11-08 12:30` / `今天 12:30`）必须置 `occurred_at=None`
   并挂 `TIME_MISSING` Issue，等待用户核对补齐；金额、收支方向缺失同理。
4. 金额一律经 `Decimal` 转成整数分（`amount_fen >= 1`），禁止浮点误差。
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import threading
from datetime import datetime
from typing import Any, Callable, NamedTuple, Protocol

from ..contracts import (
    Category,
    ClassificationSource,
    FlowType,
    Issue,
    ParseResult,
    TransactionDraft,
)
from .base import (
    ISSUE_AMOUNT_MISSING,
    ISSUE_DUPLICATE_SUSPECTED,
    ISSUE_FLOW_TYPE_UNKNOWN,
    ISSUE_INVALID_AMOUNT,
    ISSUE_INVALID_TIME,
    ISSUE_MERCHANT_MISSING,
    ISSUE_ROWS_SKIPPED,
    ISSUE_TIME_MISSING,
    INVALID_FILE,
    OCR_FIELD_MISSING,
    OCR_UNAVAILABLE,
    IntelligenceFailure,
)
from .fallback import CST, _VOID_STATUS, parse_amount_fen, parse_occurred_at

_FULL_DATE_PATTERNS = (
    re.compile(r"(20\d{2}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}(?::\d{2})?)"),
    re.compile(r"(20\d{2}[-/]\d{1,2}[-/]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)"),
    re.compile(r"(20\d{2}年\d{1,2}月\d{1,2}日(?:\s*\d{1,2}:\d{2}(?::\d{2})?)?)"),
)
_PARTIAL_DATE_PATTERNS = (
    re.compile(r"(\d{1,2}月\d{1,2}日(?:\s*\d{1,2}:\d{2}(?::\d{2})?)?)"),
    re.compile(r"(?<!\d)(\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)"),
    re.compile(r"((?:今天|昨天|前天)\s*\d{1,2}:\d{2}(?::\d{2})?)"),
)
_PRIMARY_MONEY_RE = re.compile(r"([+-]\s*[¥￥]?\s*\d[\d,]*\.\d{2}|[¥￥]\s*\d[\d,]*\.\d{2}|\d[\d,]*\.\d{2})")

_DETAIL_LABELS = (
    "账单详情",
    "支付时间",
    "付款时间",
    "创建时间",
    "交易时间",
    "交易单号",
    "商户单号",
    "订单号",
    "交易状态",
    "当前状态",
    "支付方式",
    "付款方式",
    "收款方",
    "交易对方",
    "商品说明",
)

_IGNORE_MERCHANT_EXACT = {
    "账单",
    "账单详情",
    "全部账单",
    "支出",
    "收入",
    "退款",
    "转账",
    "支付成功",
    "已存入零钱",
    "微信支付",
    "支付宝",
    "交易成功",
    "收款成功",
}


class OcrLine(NamedTuple):
    """OCR 识别出的单个文本块及其几何位置。"""

    text: str
    x_min: float
    y_center: float
    height: float
    confidence: float


class OcrEngine(Protocol):
    """OCR 引擎抽象，便于单测注入替身。"""

    def extract(self, data: bytes) -> list[OcrLine]: ...


class RapidOcrEngine:
    """基于 rapidocr-onnxruntime 的本地离线 OCR 引擎。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._engine: Any = None

    def _get_engine(self) -> Any:
        if self._engine is not None:
            return self._engine
        with self._lock:
            if self._engine is None:
                try:
                    from rapidocr_onnxruntime import RapidOCR
                except Exception as exc:  # noqa: BLE001
                    raise IntelligenceFailure(
                        OCR_UNAVAILABLE, "截图识别引擎未安装，请安装 rapidocr-onnxruntime"
                    ) from exc
                try:
                    self._engine = RapidOCR()
                except Exception as exc:  # noqa: BLE001
                    raise IntelligenceFailure(
                        OCR_UNAVAILABLE, "截图识别引擎初始化失败"
                    ) from exc
        return self._engine

    def extract(self, data: bytes) -> list[OcrLine]:
        try:
            import numpy as np
            from PIL import Image, ImageOps, UnidentifiedImageError
        except Exception as exc:  # noqa: BLE001
            raise IntelligenceFailure(OCR_UNAVAILABLE, "图像处理依赖缺失") from exc

        try:
            with Image.open(io.BytesIO(data)) as raw_img:
                img = ImageOps.exif_transpose(raw_img).convert("RGB")
                arr = np.array(img)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise IntelligenceFailure(INVALID_FILE, "截图文件损坏或无法识别为图片") from exc

        engine = self._get_engine()
        try:
            result, _ = engine(arr)
        except Exception as exc:  # noqa: BLE001
            raise IntelligenceFailure(OCR_UNAVAILABLE, "截图识别服务执行失败") from exc

        if not result:
            return []

        lines: list[OcrLine] = []
        for item in result:
            if not item or len(item) < 3:
                continue
            box, text, conf = item[0], str(item[1] or "").strip(), item[2]
            if not text:
                continue
            xs = [float(pt[0]) for pt in box]
            ys = [float(pt[1]) for pt in box]
            y_min, y_max = min(ys), max(ys)
            try:
                score = float(conf)
            except (TypeError, ValueError):
                score = 0.0
            lines.append(
                OcrLine(
                    text=text,
                    x_min=min(xs),
                    y_center=(y_min + y_max) / 2.0,
                    height=max(1.0, y_max - y_min),
                    confidence=score,
                )
            )
        return lines


def group_visual_rows(lines: list[OcrLine]) -> list[str]:
    """按视觉纵坐标聚类为从上到下的行文本（同行按 x 坐标拼合）。"""
    if not lines:
        return []
    ordered = sorted(lines, key=lambda item: (item.y_center, item.x_min))
    heights = sorted(item.height for item in ordered)
    median_h = heights[len(heights) // 2]
    y_tol = max(6.0, median_h * 0.65)

    buckets: list[list[OcrLine]] = []
    bucket_y: list[float] = []
    for line in ordered:
        placed = False
        for idx in range(len(buckets) - 1, -1, -1):
            if abs(line.y_center - bucket_y[idx]) <= y_tol:
                buckets[idx].append(line)
                bucket_y[idx] = sum(x.y_center for x in buckets[idx]) / len(buckets[idx])
                placed = True
                break
        if not placed:
            buckets.append([line])
            bucket_y.append(line.y_center)

    rows: list[str] = []
    for bucket in buckets:
        bucket.sort(key=lambda item: item.x_min)
        joined = " ".join(item.text.strip() for item in bucket if item.text.strip())
        if joined:
            rows.append(joined)
    return rows


def _normalize_ocr_datetime_text(text: str) -> str:
    """修正 OCR 常见的年月日粘连、冒号空格与日期时间粘连。"""
    out = re.sub(
        r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
        lambda m: f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}",
        text,
    )
    out = re.sub(
        r"(\d{1,2})\s*:\s*(\d{2})(?:\s*:\s*(\d{2}))?",
        lambda m: f"{m.group(1)}:{m.group(2)}" + (f":{m.group(3)}" if m.group(3) else ""),
        out,
    )
    out = re.sub(r"(20\d{2}[-/]\d{2}[-/]\d{2})\s*(\d{2}:\d{2}(?::\d{2})?)", r"\1 \2", out)
    out = re.sub(r"(?<!\d)(\d{2}[-/]\d{2})\s*(\d{2}:\d{2}(?::\d{2})?)", r"\1 \2", out)
    return out


def parse_screenshot_datetime(raw: str | None) -> tuple[datetime | None, str | None]:
    """解析截图中的时间文本。缺年份时返回 (None, 'MISSING_YEAR')，绝不猜测当前年。"""
    text = (raw or "").strip()
    if not text:
        return None, "EMPTY"

    normalized = _normalize_ocr_datetime_text(text)
    # 先尝试 ISO 8601
    try:
        iso = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        return (iso if iso.tzinfo else iso.replace(tzinfo=CST)), None
    except ValueError:
        pass

    dt = parse_occurred_at(normalized)
    if dt is not None:
        return dt, None

    # 从较长文本中抽取完整年月日
    for pat in _FULL_DATE_PATTERNS:
        m = pat.search(normalized)
        if m:
            dt = parse_occurred_at(m.group(1))
            if dt is not None:
                return dt, None

    # 明确缺年份（如 11-08 12:30、11月8日 12:30、今天 12:30）
    for pat in _PARTIAL_DATE_PATTERNS:
        if pat.search(normalized):
            return None, "MISSING_YEAR"

    return None, "INVALID"


def _infer_flow_type(
    flow_hint: str | None,
    amount_raw: str | None,
    context_text: str,
) -> FlowType | None:
    """结合显式流向、金额正负号和语义关键词推断流向，判断不出返回 None。"""
    if flow_hint:
        val = flow_hint.strip().lower()
        for member in FlowType:
            if val == member.value:
                return member

    combined = f"{flow_hint or ''} {context_text}"
    if any(k in combined for k in ("退款", "退回", "退货")):
        return FlowType.refund
    if any(k in combined for k in ("还款", "还信用卡", "花呗还款", "白条还款")):
        return FlowType.repayment
    if any(k in combined for k in ("转账", "转给", "微信红包", "群收款", "提现", "充值", "零钱通", "余额宝")):
        return FlowType.transfer

    amt_text = (amount_raw or "").strip()
    if amt_text.startswith("+"):
        return FlowType.income
    if amt_text.startswith("-"):
        return FlowType.expense

    if any(k in combined for k in ("收入", "收款成功", "已存入零钱", "工资", "奖金")):
        return FlowType.income
    if any(k in combined for k in ("支出", "支付成功", "付款成功", "当前状态 支付成功", "扣款成功", "消费")):
        return FlowType.expense
    return None


def _stable_ocr_row_id(source: str, index: int, order_id: str | None) -> str:
    if order_id:
        digest = hashlib.sha1(f"{source}:ocr:{order_id}".encode("utf-8")).hexdigest()
        return f"row_{digest[:12]}"
    return f"row_ocr{index:04d}"


def draft_from_ocr_fields(
    *,
    source: str,
    index: int,
    amount_raw: str | None,
    occurred_raw: str | None,
    flow_hint: str | None,
    merchant: str | None,
    description: str | None,
    order_id: str | None,
    status_text: str | None = None,
    context_text: str = "",
) -> tuple[TransactionDraft | None, list[Issue], bool]:
    """把 OCR/LLM 提取的原始文本字段校验并组装为 TransactionDraft。

    返回 `(draft, row_issues, skipped_as_void)`。
    """
    if status_text and any(word in status_text for word in _VOID_STATUS):
        return None, [], True

    clean_order = (order_id or "").strip() or None
    row_id = _stable_ocr_row_id(source, index, clean_order)
    row_issues: list[Issue] = []

    amt_str = (amount_raw or "").strip()
    signed_clean = amt_str.lstrip("+-").strip()
    amount_fen: int | None = parse_amount_fen(signed_clean) if signed_clean else None
    if amount_fen is None and amt_str:
        row_issues.append(
            Issue(
                row_id=row_id,
                field="amount_fen",
                code=ISSUE_INVALID_AMOUNT,
                message=f"截图金额格式无法解析：{amt_str}",
            )
        )
    elif amount_fen is None or amount_fen <= 0:
        if amount_fen is not None and amount_fen <= 0:
            return None, [], True
        amount_fen = None
        row_issues.append(
            Issue(
                row_id=row_id,
                field="amount_fen",
                code=ISSUE_AMOUNT_MISSING,
                message="截图中未识别到有效金额，请手动补全",
            )
        )

    occurred_at, time_err = parse_screenshot_datetime(occurred_raw)
    if occurred_at is None:
        if time_err == "MISSING_YEAR":
            row_issues.append(
                Issue(
                    row_id=row_id,
                    field="occurred_at",
                    code=ISSUE_TIME_MISSING,
                    message=f"截图时间缺少具体年份（{occurred_raw}），请手动补全完整日期",
                )
            )
        elif time_err == "EMPTY":
            row_issues.append(
                Issue(
                    row_id=row_id,
                    field="occurred_at",
                    code=ISSUE_TIME_MISSING,
                    message="截图中未识别到交易时间，请手动补全",
                )
            )
        else:
            row_issues.append(
                Issue(
                    row_id=row_id,
                    field="occurred_at",
                    code=ISSUE_INVALID_TIME,
                    message=f"截图时间无法解析：{occurred_raw}",
                )
            )

    flow_type = _infer_flow_type(flow_hint, amt_str, f"{merchant or ''} {description or ''} {context_text}")
    if flow_type is None:
        row_issues.append(
            Issue(
                row_id=row_id,
                field="flow_type",
                code=ISSUE_FLOW_TYPE_UNKNOWN,
                message="无法从截图确定收支方向，请手动选择",
            )
        )

    clean_merchant = (merchant or "").strip()
    if not clean_merchant:
        clean_merchant = "未知商户"
        row_issues.append(
            Issue(
                row_id=row_id,
                field="merchant",
                code=ISSUE_MERCHANT_MISSING,
                message="截图中未识别到商户名称，请手动补充",
            )
        )

    draft = TransactionDraft(
        source_transaction_id=clean_order,
        occurred_at=occurred_at,
        amount_fen=amount_fen,
        currency="CNY",
        flow_type=flow_type,
        merchant=clean_merchant,
        description=(description or "").strip(),
        category=Category.pending,
        row_id=row_id,
        classification_source=ClassificationSource.pending,
        classification_reason="截图识别待分类",
        duplicate_status="unique",
        issues=row_issues,
    )
    return draft, row_issues, False


def _extract_labeled_value(rows: list[str], labels: tuple[str, ...]) -> str | None:
    for idx, line in enumerate(rows):
        for label in labels:
            m = re.match(rf"^\s*{re.escape(label)}\s*[:：]?\s*(.*)$", line)
            if m:
                val = m.group(1).strip()
                if val:
                    return val
                if idx + 1 < len(rows):
                    nxt = rows[idx + 1].strip()
                    if nxt and not any(nxt.startswith(lb) for lb in _DETAIL_LABELS):
                        return nxt
    return None


def _is_detail_screenshot(rows: list[str]) -> bool:
    joined = "\n".join(rows)
    hits = sum(1 for lb in _DETAIL_LABELS if lb in joined)
    money_lines = [line for line in rows if _PRIMARY_MONEY_RE.search(line)]
    return hits >= 2 or (hits >= 1 and len(money_lines) <= 2)


def _scan_time_from_lines(lines: list[str]) -> str | None:
    for line in lines:
        norm = _normalize_ocr_datetime_text(line)
        for pat in _FULL_DATE_PATTERNS + _PARTIAL_DATE_PATTERNS:
            m = pat.search(norm)
            if m:
                return m.group(1)
    return None


def _parse_detail_screenshot(rows: list[str], source: str) -> ParseResult:
    joined = "\n".join(rows)
    status_text = _extract_labeled_value(rows, ("当前状态", "交易状态"))
    order_id = _extract_labeled_value(rows, ("交易单号", "订单号", "商户单号", "流水号"))
    if order_id:
        # 去掉末尾多余空格
        order_id = order_id.split()[0]

    time_raw = _extract_labeled_value(rows, ("支付时间", "付款时间", "创建时间", "交易时间", "时间"))
    if not time_raw:
        time_raw = _scan_time_from_lines(rows)

    amount_raw: str | None = None
    amount_line_idx = -1
    for idx, line in enumerate(rows):
        # 优先匹配带正负号或货币符的大金额
        m = _PRIMARY_MONEY_RE.search(line)
        if m:
            candidate = m.group(1).replace(" ", "")
            # 排除时间中的小数（通常两位小数不会是时间，但排除 100.0% 等）
            if "%" not in line:
                amount_raw = candidate
                amount_line_idx = idx
                break

    merchant = _extract_labeled_value(rows, ("交易对方", "收款方", "商户全称", "商户名称"))
    description = _extract_labeled_value(rows, ("商品说明", "商品名称", "商品", "备注", "转账说明")) or ""
    if not merchant and amount_line_idx > 0:
        for idx in range(amount_line_idx - 1, -1, -1):
            cand = rows[idx].strip()
            if (
                cand
                and cand not in _IGNORE_MERCHANT_EXACT
                and not _PRIMARY_MONEY_RE.search(cand)
                and not any(cand.startswith(lb) for lb in _DETAIL_LABELS)
            ):
                merchant = cand
                break

    if amount_raw is None and not order_id and not merchant:
        raise IntelligenceFailure(
            OCR_FIELD_MISSING, "截图中缺少必要账单字段（未识别到金额或商户）"
        )

    draft, row_issues, skipped = draft_from_ocr_fields(
        source=source,
        index=1,
        amount_raw=amount_raw,
        occurred_raw=time_raw,
        flow_hint=None,
        merchant=merchant,
        description=description,
        order_id=order_id,
        status_text=status_text,
        context_text=joined,
    )
    if skipped:
        return ParseResult(
            rows=[],
            issues=[
                Issue(
                    row_id=None,
                    field=None,
                    code=ISSUE_ROWS_SKIPPED,
                    message="已跳过 1 条无效交易（交易关闭或金额为 0）",
                )
            ],
        )
    assert draft is not None
    return ParseResult(rows=[draft], issues=list(row_issues))


def _parse_list_screenshot(rows: list[str], source: str) -> ParseResult:
    """解析多行账单列表截图：以金额锚点切块，提取商户、时间与金额。"""
    anchor_indices: list[int] = []
    for idx, line in enumerate(rows):
        if "%" in line:
            continue
        # 列表项通常带有 -38.50 / +100.00 / ¥45.00
        if re.search(r"(?:[+-]\s*[¥￥]?|[¥￥]\s*)\d[\d,]*\.\d{2}", line):
            anchor_indices.append(idx)

    if not anchor_indices:
        raise IntelligenceFailure(
            OCR_FIELD_MISSING, "截图中缺少必要账单字段，请上传清晰的微信或支付宝账单截图"
        )

    drafts: list[TransactionDraft] = []
    issues: list[Issue] = []
    void_count = 0

    for seq, anchor_idx in enumerate(anchor_indices, start=1):
        line = rows[anchor_idx]
        m_amt = re.search(r"([+-]?\s*[¥￥]?\s*\d[\d,]*\.\d{2})", line)
        amount_raw = m_amt.group(1).replace(" ", "") if m_amt else None
        left_part = line[: m_amt.start()].strip() if m_amt else line.strip()

        # 向后最多看 2 行（不能跨越下一个金额锚点）寻找时间或补充信息
        next_anchor = anchor_indices[seq] if seq < len(anchor_indices) else len(rows)
        window = [line]
        for j in range(anchor_idx + 1, min(next_anchor, anchor_idx + 3)):
            window.append(rows[j])
        block_text = " ".join(window)

        time_raw = _scan_time_from_lines(window)

        merchant = left_part
        if not merchant and anchor_idx > 0:
            prev_anchor = anchor_indices[seq - 2] if seq >= 2 else -1
            if anchor_idx - 1 > prev_anchor:
                prev_line = rows[anchor_idx - 1].strip()
                if prev_line and prev_line not in _IGNORE_MERCHANT_EXACT:
                    merchant = prev_line

        # 去掉商户尾部可能粘连的时间文本
        if time_raw and merchant and time_raw in merchant:
            merchant = merchant.replace(time_raw, "").strip()

        status_text = block_text if any(w in block_text for w in _VOID_STATUS) else None
        draft, row_issues, skipped = draft_from_ocr_fields(
            source=source,
            index=seq,
            amount_raw=amount_raw,
            occurred_raw=time_raw,
            flow_hint=None,
            merchant=merchant,
            description="",
            order_id=None,
            status_text=status_text,
            context_text=block_text,
        )
        if skipped:
            void_count += 1
            continue
        if draft is not None:
            drafts.append(draft)
            issues.extend(row_issues)

    if void_count:
        issues.append(
            Issue(
                row_id=None,
                field=None,
                code=ISSUE_ROWS_SKIPPED,
                message=f"已跳过 {void_count} 行无效交易（交易关闭或金额为 0）",
            )
        )
    return ParseResult(rows=drafts, issues=issues)


def parse_ocr_lines_deterministic(visual_rows: list[str], source: str) -> ParseResult:
    """将按行排列的 OCR 文本转为 ParseResult。"""
    cleaned = [row.strip() for row in visual_rows if row and row.strip()]
    if not cleaned:
        raise IntelligenceFailure(OCR_FIELD_MISSING, "截图中未识别到有效文字")

    if _is_detail_screenshot(cleaned):
        return _parse_detail_screenshot(cleaned, source)
    return _parse_list_screenshot(cleaned, source)


def parse_llm_ocr_payload(raw_json: str, source: str) -> ParseResult:
    """校验并转换 DeepSeek 从 OCR 文本结构化抽取的 JSON 结果。"""
    try:
        payload = json.loads(raw_json)
    except ValueError as exc:
        raise ValueError("LLM OCR 输出不是合法 JSON") from exc

    raw_items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("LLM OCR 输出缺少 items 列表")

    drafts: list[TransactionDraft] = []
    issues: list[Issue] = []
    seen_orders: set[str] = set()
    void_count = 0

    for idx, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue
        order_id = str(item.get("source_transaction_id") or "").strip() or None
        draft, row_issues, skipped = draft_from_ocr_fields(
            source=source,
            index=idx,
            amount_raw=str(item.get("amount_raw") or "").strip() or None,
            occurred_raw=str(item.get("occurred_at_raw") or "").strip() or None,
            flow_hint=str(item.get("flow_type") or "").strip() or None,
            merchant=str(item.get("merchant") or "").strip() or None,
            description=str(item.get("description") or "").strip() or None,
            order_id=order_id,
            status_text=str(item.get("status") or "").strip() or None,
            context_text=str(item.get("context") or ""),
        )
        if skipped:
            void_count += 1
            continue
        if draft is None:
            continue
        if order_id:
            if order_id in seen_orders:
                dup_issue = Issue(
                    row_id=draft.row_id,
                    field="source_transaction_id",
                    code=ISSUE_DUPLICATE_SUSPECTED,
                    message="同一截图内出现相同交易单号，请核对是否重复",
                )
                draft = draft.model_copy(
                    update={
                        "duplicate_status": "suspected",
                        "issues": list(draft.issues) + [dup_issue],
                    }
                )
                row_issues.append(dup_issue)
            seen_orders.add(order_id)
        drafts.append(draft)
        issues.extend(row_issues)

    if void_count:
        issues.append(
            Issue(
                row_id=None,
                field=None,
                code=ISSUE_ROWS_SKIPPED,
                message=f"已跳过 {void_count} 行无效交易（交易关闭或金额为 0）",
            )
        )
    if not drafts and not void_count:
        raise IntelligenceFailure(OCR_FIELD_MISSING, "截图中缺少必要账单字段")
    return ParseResult(rows=drafts, issues=issues)


def extract_bill_from_image(
    data: bytes,
    source: str,
    *,
    ocr_engine: OcrEngine,
    llm_structurer: Callable[[list[str], str], str] | None = None,
) -> ParseResult:
    """截图识别总入口：先离线 OCR 提字，可选 DeepSeek 结构化，失败回退确定性解析。"""
    lines = ocr_engine.extract(data)
    visual_rows = group_visual_rows(lines)
    if not visual_rows:
        raise IntelligenceFailure(OCR_FIELD_MISSING, "截图中未识别到有效文字")

    if llm_structurer is not None:
        try:
            raw_json = llm_structurer(visual_rows, source)
            return parse_llm_ocr_payload(raw_json, source)
        except IntelligenceFailure:
            # 确定性解析仍可兜底整图
            pass
        except Exception:
            pass

    return parse_ocr_lines_deterministic(visual_rows, source)
