"""本地 OCR。识别结果只生成待确认草稿，绝不直接入账。"""
from __future__ import annotations

import io
import re
import uuid
from functools import lru_cache

from PIL import Image

from ..contracts import Category, ClassificationSource, FlowType, Issue, ParseResult, TransactionDraft
from .base import IntelligenceFailure, OCR_UNAVAILABLE, ISSUE_TIME_MISSING, ISSUE_FLOW_TYPE_UNKNOWN
from .fallback import FallbackIntelligence, parse_amount_fen, parse_occurred_at

_MONEY = re.compile(r"(?<![\d./-])(?:[¥￥]\s*)?\d[\d,]*\.\d{2}(?![\d./-])")
_DATE = re.compile(r"\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?\s*\d{1,2}:\d{2}(?::\d{2})?")


@lru_cache(maxsize=1)
def _engine():
    from rapidocr import RapidOCR
    return RapidOCR()


class LocalOCRIntelligence(FallbackIntelligence):
    name = "local-rapidocr"

    def recognize_bill_image(self, data: bytes, mime_type: str, source: str) -> ParseResult:
        try:
            image = Image.open(io.BytesIO(data))
            if image.format not in ("PNG", "JPEG"):
                raise ValueError("image format")
            image.verify()
            result = _engine()(data)
            lines = [str(value).strip() for value in (result.txts or ()) if str(value).strip()]
        except Exception as exc:
            raise IntelligenceFailure(OCR_UNAVAILABLE, "图片识别失败，请检查图片是否清晰") from exc
        if not lines:
            raise IntelligenceFailure(OCR_UNAVAILABLE, "未识别到交易文字，请换一张清晰截图")

        # 同一张截图可以有多笔：按金额所在行建草稿；时间和商户从邻近文字补充。
        rows: list[TransactionDraft] = []
        issues: list[Issue] = []
        for index, line in enumerate(lines):
            amounts = _MONEY.findall(line)
            if not amounts:
                continue
            nearby = " ".join(lines[max(0,index-2):min(len(lines),index+3)])
            date_match = _DATE.search(nearby)
            raw_date = date_match.group(0) if date_match else ""
            raw_date = raw_date.replace("年", "-").replace("月", "-").replace("日", "")
            occurred = parse_occurred_at(raw_date) if raw_date else None
            amount = parse_amount_fen(amounts[-1])
            if amount is None or amount <= 0:
                continue
            flow = (FlowType.refund if "退款" in nearby else
                    FlowType.income if any(x in nearby for x in ("收入", "收款", "到账")) else
                    FlowType.expense if any(x in nearby for x in ("支出", "付款", "支付")) else None)
            row_id = f"ocr_{index}_{uuid.uuid4().hex[:8]}"
            row_issues = []
            if occurred is None:
                row_issues.append(Issue(row_id=row_id, field="occurred_at",
                    code=ISSUE_TIME_MISSING, message="截图中未识别到完整交易时间，请手动填写"))
            if flow is None:
                row_issues.append(Issue(row_id=row_id, field="flow_type",
                    code=ISSUE_FLOW_TYPE_UNKNOWN, message="无法判断收支方向，请手动选择"))
            merchant = re.sub(_MONEY, "", line).strip(" ：: -") or "待核对商户"
            rows.append(TransactionDraft(source_transaction_id=None, occurred_at=occurred,
                amount_fen=amount, currency="CNY", flow_type=flow, merchant=merchant[:500],
                description=line[:2000], category=Category.pending, row_id=row_id,
                classification_source=ClassificationSource.pending,
                classification_reason="OCR 识别结果，待确认", duplicate_status="suspected",
                issues=row_issues))
            issues.extend(row_issues)
        if not rows:
            raise IntelligenceFailure(OCR_UNAVAILABLE, "未找到可识别金额，请手动检查截图")
        return ParseResult(rows=rows[:500], issues=issues)
