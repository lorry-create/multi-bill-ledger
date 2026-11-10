"""确定性兜底实现：不联网、不调模型，纯规则跑通「文件 → 待确认草稿 → 分类」。

存在的理由有两个，都很实际：

1. **D 没到位时后端不能停工。** T02 的五个接口要拿真实行验收，等不到别人的模块。
2. **模型挂了业务不能停。** DeepSeek 超时或返回非法时，交易必须有一条诚实的
   `general_rule` 路径，而不是卡在 pending 里烂掉（docs/08 A06 明确禁止伪成功）。

它不被命名为"mock"：mock 暗示数据是假的。这里的**解析和金额是真的**，
只是分类用关键词而非模型，并且 `classification_source` 如实写 `general_rule`。
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from ..contracts import (
    Category,
    ClassificationResult,
    ClassificationRule,
    ClassificationSource,
    FlowType,
    IngestionMethod,
    Issue,
    ParseResult,
    TransactionDraft,
)
from .base import (
    ISSUE_AMOUNT_MISSING,
    ISSUE_CATEGORY_UNCERTAIN,
    ISSUE_DUPLICATE_SUSPECTED,
    ISSUE_FLOW_TYPE_UNKNOWN,
    ISSUE_INVALID_TIME,
    ISSUE_ROWS_SKIPPED,
    ISSUE_TIME_MISSING,
    OCR_UNAVAILABLE,
    UNSUPPORTED_TEMPLATE,
    IntelligenceFailure,
)
from .normalize import normalize_merchant
from .rules import classify_by_keywords
from .tables import Table, find_header, index_of, load_table

CST = timezone(timedelta(hours=8))

# 平台差异集中在这张表里，加新平台只改这里
_PLATFORM_COLUMNS = {
    "alipay": {
        "required": ("交易号", "交易创建时间"),
        "time": ("交易创建时间", "付款时间"),
        "merchant": ("交易对方",),
        "description": ("商品名称",),
        "amount": ("金额(元)", "金额"),
        "flow": ("收/支",),
        "order_id": ("交易号",),
        "status": ("交易状态",),
    },
    "wechat": {
        "required": ("交易时间", "交易单号"),
        "time": ("交易时间",),
        "merchant": ("交易对方",),
        "description": ("商品",),
        "amount": ("金额(元)", "金额"),
        "flow": ("收/支",),
        "order_id": ("交易单号",),
        "status": ("当前状态",),
    },
}

# 这些状态说明钱没真正发生，不该入账
_VOID_STATUS = ("交易关闭", "已关闭", "支付失败", "已撤销", "交易失败")

_TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
)


def parse_amount_fen(raw: str) -> int | None:
    """把「¥1,234.56」这类金额串转成整数分。解析不了返回 None，不抛异常。

    用 Decimal 而不是 float：0.1 + 0.2 的问题在这里会变成真实的账目误差，
    而金额是要逐笔和人工核对的（docs/08 A02）。
    """
    text = (raw or "").strip()
    if not text:
        return None
    for noise in ("¥", "￥", ",", " ", "元", "CNY", "RMB"):
        text = text.replace(noise, "")
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return int((value * 100).to_integral_value(rounding="ROUND_HALF_UP"))


def parse_occurred_at(raw: str) -> datetime | None:
    """解析平台时间串并按 Asia/Shanghai 归月。认不出返回 None。"""
    text = (raw or "").strip()
    if not text:
        return None
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=CST)
        except ValueError:
            continue
    return None


def _flow_from_text(raw: str) -> FlowType | None:
    text = (raw or "").strip()
    if text in ("收入", "收"):
        return FlowType.income
    if text in ("支出", "支"):
        return FlowType.expense
    if text in ("不计收支", "/", "中性交易", "其他"):
        return FlowType.transfer
    return None


def _row_id_for(source: str, order_id: str, line_no: int) -> str:
    """草稿行标识。有单号就按单号派生，没有才退回行号。

    按单号派生意味着同一份文件重复解析、或用户重传同一文件，row_id 都一样，
    F 端不会因为刷新而丢掉已填的编辑（docs/11：row_id 稳定，不能依赖数组顺序）。
    """
    if order_id:
        digest = hashlib.sha1(f"{source}:{order_id}".encode("utf-8")).hexdigest()
        return f"row_{digest[:12]}"
    return f"row_line{line_no:04d}"


def _cell(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index]


class FallbackIntelligence:
    """满足 IntelligenceProvider 协议的最小实现。"""

    name = "fallback-rules"

    # ---- 文件解析 ----

    def parse_bill_file(self, data: bytes, filename: str, source: str) -> ParseResult:
        rows = load_table(data, filename)
        table, platform = self._locate_table(rows, source)
        return self._to_drafts(table, platform)

    def _locate_table(self, rows: list[list[str]], source: str) -> tuple[Table, str]:
        """先按声明的 source 找表头，找不到再容忍一次错标。

        用户把支付宝文件标成微信是常见操作失误。与其报"模板不支持"，不如按内容
        认出来，但仍以真实平台入库——平台属性直接影响去重范围，不能将错就错。
        """
        order = [source] + [name for name in _PLATFORM_COLUMNS if name != source]
        last_error: IntelligenceFailure | None = None
        for name in order:
            columns = _PLATFORM_COLUMNS.get(name)
            if columns is None:
                continue
            try:
                return find_header(rows, columns["required"]), name
            except IntelligenceFailure as exc:
                last_error = exc
        raise last_error or IntelligenceFailure(UNSUPPORTED_TEMPLATE)

    def _to_drafts(self, table: Table, platform: str) -> ParseResult:
        columns = _PLATFORM_COLUMNS[platform]
        header = table.header
        idx = {key: index_of(header, *value) for key, value in columns.items() if key != "required"}

        drafts: list[TransactionDraft] = []
        issues: list[Issue] = []
        seen_orders: set[str] = set()
        void_count = 0

        for offset, row in enumerate(table.rows):
            line_no = table.header_line + offset + 1
            status = _cell(row, idx["status"])
            if any(word in status for word in _VOID_STATUS):
                void_count += 1
                continue

            order_id = _cell(row, idx["order_id"]).strip()
            amount = parse_amount_fen(_cell(row, idx["amount"]))
            occurred_raw = _cell(row, idx["time"])
            occurred_at = parse_occurred_at(occurred_raw)

            # 金额为 0 或空：0 元订单（优惠券、积分兑换）不是真实账目，跳过不入草稿，
            # 否则确认阶段会因 amount_fen >= 1 全军覆没
            if amount is None or amount <= 0:
                if amount is not None and amount <= 0:
                    void_count += 1
                    continue
                issues.append(
                    Issue(
                        row_id=None,
                        field="amount_fen",
                        code=ISSUE_AMOUNT_MISSING,
                        message=f"第 {line_no} 行金额为空或无法解析，未生成草稿",
                    )
                )
                continue

            row_id = _row_id_for(platform, order_id, line_no)
            row_issues: list[Issue] = []

            if occurred_at is None:
                code = ISSUE_TIME_MISSING if not occurred_raw else ISSUE_INVALID_TIME
                row_issues.append(
                    Issue(
                        row_id=row_id,
                        field="occurred_at",
                        code=code,
                        message=f"交易时间无法解析：{occurred_raw or '空'}",
                    )
                )

            flow_type = _flow_from_text(_cell(row, idx["flow"]))
            description = _cell(row, idx["description"]) or ""
            merchant = _cell(row, idx["merchant"]) or ""

            # 收入方向且说明含「退款」的，按退款计——月报里退款是独立口径，
            # 混进收入会把"工资收入"算高（docs 的 Totals 定义）
            if flow_type == FlowType.income and "退款" in f"{status} {description}":
                flow_type = FlowType.refund

            if flow_type is None:
                row_issues.append(
                    Issue(
                        row_id=row_id,
                        field="flow_type",
                        code=ISSUE_FLOW_TYPE_UNKNOWN,
                        message=f"无法判断收支方向：{_cell(row, idx['flow']) or '空'}",
                    )
                )

            duplicate = "unique"
            if order_id:
                if order_id in seen_orders:
                    duplicate = "duplicate"
                    row_issues.append(
                        Issue(
                            row_id=row_id,
                            field="source_transaction_id",
                            code=ISSUE_DUPLICATE_SUSPECTED,
                            message="同一文件内出现相同交易单号",
                        )
                    )
                seen_orders.add(order_id)

            drafts.append(
                TransactionDraft(
                    source_transaction_id=order_id or None,
                    occurred_at=occurred_at,
                    amount_fen=amount,
                    currency="CNY",
                    flow_type=flow_type,
                    merchant=merchant or "未知商户",
                    description=description,
                    # 解析阶段不猜类别，统一进 pending 桶，由 classify 决定
                    category=Category.pending,
                    row_id=row_id,
                    classification_source=ClassificationSource.pending,
                    classification_reason="待分类",
                    duplicate_status=duplicate,
                    issues=row_issues,
                )
            )
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

    def recognize_bill_image(self, data: bytes, mime_type: str, source: str) -> ParseResult:
        """截图识别需要 OCR，兜底实现不提供，明确失败而不是返回空结果。"""
        raise IntelligenceFailure(OCR_UNAVAILABLE, "当前未接入截图识别，请上传平台导出的文件")

    # ---- 分类 ----

    def normalize_merchant(self, raw: str) -> str:
        return normalize_merchant(raw)

    def classify_transactions(
        self,
        rows: list[TransactionDraft],
        rules: list[ClassificationRule],
        use_llm: bool = False,
    ) -> list[ClassificationResult]:
        """优先级：本人规则 > 通用规则 > 待确认。

        调用约定：`rules` 必须是**当前批次所属平台 + 当前用户 + enabled** 的规则。
        TransactionDraft 上没有 source 字段（契约如此），所以这里无法按平台过滤；
        由调用方筛好比在这里猜更可靠，否则同一商户名会在支付宝和微信之间串用。

        use_llm 在兜底实现里被忽略——宁可返回 pending 也不伪造一个 `deepseek`
        来源，那是 docs/08 A06 点名禁止的伪成功。
        """
        by_merchant: dict[str, ClassificationRule] = {}
        for rule in rules:
            if rule.enabled and rule.source is not None:
                by_merchant.setdefault(rule.merchant_normalized, rule)

        results: list[ClassificationResult] = []
        for row in rows:
            hit = by_merchant.get(normalize_merchant(row.merchant))
            if hit is not None:
                results.append(
                    ClassificationResult(
                        row_id=row.row_id,
                        category=hit.category,
                        classification_source=ClassificationSource.user_rule,
                        classification_reason=f"命中本人规则（{hit.merchant_normalized}）",
                        issues=[],
                    )
                )
                continue

            matched = classify_by_keywords(row.merchant, row.description, row.flow_type)
            if matched is not None:
                category, reason = matched
                results.append(
                    ClassificationResult(
                        row_id=row.row_id,
                        category=category,
                        classification_source=ClassificationSource.general_rule,
                        classification_reason=reason,
                        issues=[],
                    )
                )
                continue

            results.append(
                ClassificationResult(
                    row_id=row.row_id,
                    category=Category.pending,
                    classification_source=ClassificationSource.pending,
                    classification_reason="通用规则未命中，待用户确认",
                    issues=[
                        Issue(
                            row_id=row.row_id,
                            field="category",
                            code=ISSUE_CATEGORY_UNCERTAIN,
                            message="无法自动判断类别，请手动选择",
                        )
                    ],
                )
            )
        return results
