"""智能模块（intelligence）的公共契约。

本文件是 H（后端）与 D（数据/智能）之间的接口边界，对应 docs/13「智能模块接口」。
它只定义"长什么样"，不实现解析算法。

分工纪律：
- D 实现 parse_bill_file / recognize_bill_image / normalize_merchant / classify_transactions；
- H 只通过本文件的 Protocol 调用，不 import D 的具体模块，也不复制解析逻辑；
- 任何一方要改签名，先改 docs/13 再改这里，同一 PR 更新两端（AGENTS.md）。

异常约定（docs/13 末尾）：文件整体无法解析时抛 IntelligenceFailure，带稳定 code 和
**安全 message**。异常消息里不允许出现密钥、原文件内容或用户明文。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..contracts import (
    ClassificationResult,
    ClassificationRule,
    ParseResult,
    TransactionDraft,
)

# ---- 异常代码：docs/13 约定的六个最小集合，不得随意扩展 ----
UNSUPPORTED_TEMPLATE = "UNSUPPORTED_TEMPLATE"
INVALID_FILE = "INVALID_FILE"
OCR_UNAVAILABLE = "OCR_UNAVAILABLE"
OCR_FIELD_MISSING = "OCR_FIELD_MISSING"
MODEL_TIMEOUT = "MODEL_TIMEOUT"
MODEL_OUTPUT_INVALID = "MODEL_OUTPUT_INVALID"

SAFE_MESSAGES = {
    UNSUPPORTED_TEMPLATE: "无法识别该账单模板，请确认是从支付平台导出的原始文件",
    INVALID_FILE: "文件内容不合法或已损坏",
    OCR_UNAVAILABLE: "截图识别服务当前不可用",
    OCR_FIELD_MISSING: "截图中缺少必要字段",
    MODEL_TIMEOUT: "智能分类服务响应超时",
    MODEL_OUTPUT_INVALID: "智能分类返回结果不符合约定格式",
}

# ---- Issue.code：给前端做逻辑判断的稳定机器码 ----
# 契约示例里只出现过 INVALID_AMOUNT，其余为本项目补充，已记入 docs/20。
ISSUE_AMOUNT_MISSING = "AMOUNT_MISSING"
ISSUE_INVALID_AMOUNT = "INVALID_AMOUNT"
ISSUE_TIME_MISSING = "TIME_MISSING"
ISSUE_INVALID_TIME = "INVALID_TIME"
ISSUE_FLOW_TYPE_UNKNOWN = "FLOW_TYPE_UNKNOWN"
ISSUE_MERCHANT_MISSING = "MERCHANT_MISSING"
ISSUE_CATEGORY_UNCERTAIN = "CATEGORY_UNCERTAIN"
ISSUE_ROW_UNPARSABLE = "ROW_UNPARSABLE"
ISSUE_DUPLICATE_SUSPECTED = "DUPLICATE_SUSPECTED"
# 说明行/关闭交易被跳过时，用一条 row_id 为 null 的 Issue 告知用户"少了哪些"，
# 避免"文件里 30 条、界面 27 条"这种说不清的数量差
ISSUE_ROWS_SKIPPED = "ROWS_SKIPPED"


class IntelligenceFailure(RuntimeError):
    """智能模块无法继续时的统一异常。

    只允许携带已登记的 code 与固定安全文案；不接受把原始异常、文件内容或
    用户数据塞进 message——那些会进日志、进响应、进工单截图。
    """

    def __init__(self, code: str, message: str | None = None) -> None:
        if code not in SAFE_MESSAGES:
            raise ValueError(f"未登记的错误代码：{code}")
        self.code = code
        # 默认用登记文案；允许传更具体的安全说明，但仍是调用方自己写的固定串
        self.message = message or SAFE_MESSAGES[code]
        super().__init__(self.message)

    def as_detail(self) -> dict[str, str]:
        """交给 HTTP 层转成契约 Error 的形态。"""
        return {"code": self.code, "message": self.message}


@runtime_checkable
class IntelligenceProvider(Protocol):
    """智能能力的唯一入口。

    D 的任意实现只要满足本协议即可被后端替换使用；fallback 也满足它，
    因此"D 没到位"不会阻塞 H 打通闭环。
    """

    name: str

    def parse_bill_file(self, data: bytes, filename: str, source: str) -> ParseResult:
        """解析账单文件。只读，不写库，不返回 HTTP 结构。"""
        ...

    def recognize_bill_image(self, data: bytes, mime_type: str, source: str) -> ParseResult:
        """识别账单截图。字段未知时置 null 并给 Issue，不得猜值。"""
        ...

    def normalize_merchant(self, raw: str) -> str:
        """商户名标准化，用于个人规则精确匹配。"""
        ...

    def classify_transactions(
        self,
        rows: list[TransactionDraft],
        rules: list[ClassificationRule],
        use_llm: bool = False,
    ) -> list[ClassificationResult]:
        """为每个输入 row_id 恰好返回一项，顺序与输入一致。"""
        ...


def assert_one_result_per_row(
    rows: list[TransactionDraft], results: list[ClassificationResult]
) -> None:
    """校验分类结果与草稿行一一对应。

    docs/13：模型输出的 row_id 缺失、重复或未知不能错配，相关行回 pending。
    这里做硬校验而不是默默丢弃——错配会把甲商户的类别写到乙头上，
    比分类失败严重得多。
    """
    want = [row.row_id for row in rows]
    got = [item.row_id for item in results]
    if len(got) != len(want):
        raise IntelligenceFailure(
            MODEL_OUTPUT_INVALID, f"分类结果数量不匹配：期望 {len(want)} 项，实际 {len(got)} 项"
        )
    if len(set(got)) != len(got):
        raise IntelligenceFailure(MODEL_OUTPUT_INVALID, "分类结果存在重复 row_id")
    missing = set(want) - set(got)
    unknown = set(got) - set(want)
    if missing or unknown:
        raise IntelligenceFailure(
            MODEL_OUTPUT_INVALID,
            f"分类结果 row_id 不匹配：缺少 {len(missing)} 项，多出 {len(unknown)} 项",
        )
