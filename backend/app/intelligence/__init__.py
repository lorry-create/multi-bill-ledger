"""智能模块边界（H 与 D 的接口）。

后端只从这里拿能力，不直接 import D 的具体模块：

    from app.intelligence import build_intelligence, IntelligenceFailure

    provider = build_intelligence()
    result = provider.parse_bill_file(data, filename, source)

字段定义在 `app.contracts`（由 openapi.json 生成），两边共用同一份，
不存在"后端一套、算法一套"的字段漂移。
"""

from __future__ import annotations

from .base import (
    ISSUE_AMOUNT_MISSING,
    ISSUE_CATEGORY_UNCERTAIN,
    ISSUE_DUPLICATE_SUSPECTED,
    ISSUE_FLOW_TYPE_UNKNOWN,
    ISSUE_INVALID_AMOUNT,
    ISSUE_INVALID_TIME,
    ISSUE_MERCHANT_MISSING,
    ISSUE_ROWS_SKIPPED,
    ISSUE_ROW_UNPARSABLE,
    ISSUE_TIME_MISSING,
    MODEL_OUTPUT_INVALID,
    MODEL_TIMEOUT,
    OCR_FIELD_MISSING,
    OCR_UNAVAILABLE,
    SAFE_MESSAGES,
    UNSUPPORTED_TEMPLATE,
    INVALID_FILE,
    IntelligenceFailure,
    IntelligenceProvider,
    assert_one_result_per_row,
)
from .factory import ProviderNotAvailable, build_intelligence
from .fallback import FallbackIntelligence
from .normalize import normalize_merchant

__all__ = [
    "IntelligenceFailure",
    "IntelligenceProvider",
    "ProviderNotAvailable",
    "FallbackIntelligence",
    "build_intelligence",
    "normalize_merchant",
    "assert_one_result_per_row",
    "SAFE_MESSAGES",
    # 异常代码
    "UNSUPPORTED_TEMPLATE",
    "INVALID_FILE",
    "OCR_UNAVAILABLE",
    "OCR_FIELD_MISSING",
    "MODEL_TIMEOUT",
    "MODEL_OUTPUT_INVALID",
    # Issue 代码
    "ISSUE_AMOUNT_MISSING",
    "ISSUE_INVALID_AMOUNT",
    "ISSUE_TIME_MISSING",
    "ISSUE_INVALID_TIME",
    "ISSUE_FLOW_TYPE_UNKNOWN",
    "ISSUE_MERCHANT_MISSING",
    "ISSUE_CATEGORY_UNCERTAIN",
    "ISSUE_ROW_UNPARSABLE",
    "ISSUE_DUPLICATE_SUSPECTED",
    "ISSUE_ROWS_SKIPPED",
]
