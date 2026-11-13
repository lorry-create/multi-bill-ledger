"""共用模型：由 tools/gen_pydantic_models.py 从 contracts/openapi.json 生成。

契约版本：0.2.0
不要手改本文件。改契约后执行：python tools/gen_pydantic_models.py
D 侧（backend/app/intelligence）从这里导入 ParseResult、TransactionDraft 等类型，
不得另定义一套金额单位或类别枚举。
"""

from datetime import date as _date, datetime as _datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictInt

CONTRACT_VERSION = "0.2.0"

__all__ = [
    "Source",
    "IngestionMethod",
    "Category",
    "FlowType",
    "ClassificationSource",
    "BatchStatus",
    "ResolvedCategory",
    "FieldError",
    "ErrorDetails",
    "ErrorError",
    "Error",
    "User",
    "LoginInput",
    "Session",
    "Issue",
    "TransactionInput",
    "TransactionDraft",
    "ParseResult",
    "ClassificationResult",
    "Transaction",
    "Progress",
    "Batch",
    "ConfirmRow",
    "ConfirmInput",
    "ConfirmResult",
    "RetryInput",
    "ResolveMissingInput",
    "TransactionPatchChanges",
    "TransactionPatch",
    "TransactionPage",
    "ClassificationRule",
    "RuleList",
    "RulePatch",
    "BudgetInput",
    "Budget",
    "BudgetStatus",
    "Totals",
    "MonthlyReportExpenseByCategoryItem",
    "MonthlyReportDailyTrendItem",
    "MonthlyReport",
]

class Source(str, Enum):
    """共享模型 Source；HTTP请求与响应均遵守本定义。"""

    alipay = "alipay"
    wechat = "wechat"

class IngestionMethod(str, Enum):
    """共享模型 IngestionMethod；HTTP请求与响应均遵守本定义。"""

    file = "file"
    screenshot = "screenshot"

class Category(str, Enum):
    """共享模型 Category；HTTP请求与响应均遵守本定义。"""

    dining = "dining"
    transport = "transport"
    shopping = "shopping"
    salary = "salary"
    housing = "housing"
    entertainment = "entertainment"
    health = "health"
    education = "education"
    other = "other"
    pending = "pending"

class FlowType(str, Enum):
    """共享模型 FlowType；HTTP请求与响应均遵守本定义。"""

    income = "income"
    expense = "expense"
    refund = "refund"
    transfer = "transfer"
    repayment = "repayment"

class ClassificationSource(str, Enum):
    """共享模型 ClassificationSource；HTTP请求与响应均遵守本定义。"""

    user_rule = "user_rule"
    general_rule = "general_rule"
    deepseek = "deepseek"
    manual = "manual"
    pending = "pending"

class BatchStatus(str, Enum):
    """共享模型 BatchStatus；HTTP请求与响应均遵守本定义。"""

    uploaded = "uploaded"
    processing = "processing"
    pending_review = "pending_review"
    completed = "completed"
    failed = "failed"

class FieldError(BaseModel):
    """共享模型 FieldError；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    field: str = Field(..., description="字段路径，例如rows[0].amount_fen或amount_fen。")
    row_id: Optional[str] = Field(..., description="本批次内稳定的草稿行标识，确认和分类按它关联，不能依赖数组顺序。")
    code: str = Field(..., description="稳定的机器错误代码，前端不能按中文message判断逻辑。")
    message: str = Field(..., description="面向用户的说明文本。")

class ErrorDetails(BaseModel):
    """共享模型 ErrorDetails；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    fields: Optional[list[FieldError]] = Field(default=None, description="逐字段错误列表，row_id为null表示非草稿字段。")
    current_version: Optional[int] = Field(default=None, ge=1, description="发生版本冲突时可返回当前版本；不存在此信息时省略。")
    retry_after_seconds: Optional[int] = Field(default=None, ge=1, description="限流等待秒数；不存在此信息时省略。")

class ErrorError(BaseModel):
    """error字段，类型和必填性如下。"""
    model_config = ConfigDict(extra="forbid")

    code: str = Field(...)
    message: str = Field(...)
    details: ErrorDetails = Field(...)

class Error(BaseModel):
    """共享模型 Error；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    error: ErrorError = Field(..., description="error字段，类型和必填性如下。")

class User(BaseModel):
    """共享模型 User；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="服务端资源标识，前端原样使用，不自行拼接。")
    username: str = Field(..., description="登录账号名称；不是GitHub协作者身份。")

class LoginInput(BaseModel):
    """共享模型 LoginInput；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    username: str = Field(..., min_length=1, description="登录账号名称；不是GitHub协作者身份。")
    password: str = Field(..., min_length=1, description="账号密码，只用于登录请求，不回显、不记录。")

class Session(BaseModel):
    """共享模型 Session；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    user: User = Field(..., description="当前登录用户，不包含密码或服务端密钥。")
    csrf_token: str = Field(..., description="前端保存在会话状态，写请求放入X-CSRF-Token，退出后清除。")

class Issue(BaseModel):
    """共享模型 Issue；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    row_id: Optional[str] = Field(..., description="本批次内稳定的草稿行标识，确认和分类按它关联，不能依赖数组顺序。")
    field: Optional[str] = Field(..., description="字段路径，例如rows[0].amount_fen或amount_fen。")
    code: str = Field(..., description="稳定的机器错误代码，前端不能按中文message判断逻辑。")
    message: str = Field(..., description="面向用户的说明文本。")

class TransactionInput(BaseModel):
    """共享模型 TransactionInput；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    source_transaction_id: Optional[str] = Field(..., description="可靠的源交易或退款事件标识；只有共用订单号且无法区分事件时为null并标疑似，不冒充唯一事件号。")
    occurred_at: _datetime = Field(..., description="带时区的交易时间，按Asia/Shanghai归属日期月份；草稿未知可为null。")
    amount_fen: StrictInt = Field(..., ge=1, description="CNY整数分，不是浮点元；草稿可未知，确认必须为正整数。")
    currency: Literal["CNY"] = Field(..., description="初赛只接受CNY，不自动换汇。")
    flow_type: FlowType = Field(..., description="收入、支出、退款、内部转账、还款；草稿可未知，确认前必须明确。")
    merchant: str = Field(..., max_length=500, description="商户原始展示名称；建立个人规则要求非空。")
    description: str = Field(..., max_length=2000, description="交易说明，空说明用空字符串。")
    category: Category = Field(..., description="固定类别代码；pending可作为未分类桶，但建立个人规则不接受pending。")

class TransactionDraft(BaseModel):
    """共享模型 TransactionDraft；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    source_transaction_id: Optional[str] = Field(..., description="可靠的源交易或退款事件标识；只有共用订单号且无法区分事件时为null并标疑似，不冒充唯一事件号。")
    occurred_at: Optional[_datetime] = Field(..., description="带时区的交易时间，按Asia/Shanghai归属日期月份；草稿未知可为null。")
    amount_fen: Optional[StrictInt] = Field(..., ge=1, description="CNY整数分，不是浮点元；草稿可未知，确认必须为正整数。")
    currency: Literal["CNY"] = Field(..., description="初赛只接受CNY，不自动换汇。")
    flow_type: Optional[FlowType] = Field(..., description="收入、支出、退款、内部转账、还款；草稿可未知，确认前必须明确。")
    merchant: str = Field(..., max_length=500, description="商户原始展示名称；建立个人规则要求非空。")
    description: str = Field(..., max_length=2000, description="交易说明，空说明用空字符串。")
    category: Category = Field(..., description="固定类别代码；pending可作为未分类桶，但建立个人规则不接受pending。")
    row_id: str = Field(..., description="本批次内稳定的草稿行标识，确认和分类按它关联，不能依赖数组顺序。")
    classification_source: ClassificationSource = Field(..., description="实际分类来源，不得将规则或测试替身标成deepseek。")
    classification_reason: str = Field(..., description="供用户查看的简短分类依据，不是准确率或概率。")
    duplicate_status: Literal["unique", "duplicate", "suspected"] = Field(..., description="unique可正常选中，duplicate明确重复会跳过，suspected需要人工判断。")
    issues: list[Issue] = Field(..., description="解析、识别或分类的字段问题；空数组表示暂无问题。")

class ParseResult(BaseModel):
    """共享模型 ParseResult；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    rows: list[TransactionDraft] = Field(..., description="草稿或本次选中的确认行；处理中的批次可为空数组。")
    issues: list[Issue] = Field(..., description="解析、识别或分类的字段问题；空数组表示暂无问题。")

class ClassificationResult(BaseModel):
    """共享模型 ClassificationResult；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    row_id: str = Field(..., description="本批次内稳定的草稿行标识，确认和分类按它关联，不能依赖数组顺序。")
    category: Category = Field(..., description="固定类别代码；pending可作为未分类桶，但建立个人规则不接受pending。")
    classification_source: ClassificationSource = Field(..., description="实际分类来源，不得将规则或测试替身标成deepseek。")
    classification_reason: str = Field(..., description="供用户查看的简短分类依据，不是准确率或概率。")
    issues: list[Issue] = Field(..., description="解析、识别或分类的字段问题；空数组表示暂无问题。")

class Transaction(BaseModel):
    """共享模型 Transaction；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    source_transaction_id: Optional[str] = Field(..., description="可靠的源交易或退款事件标识；只有共用订单号且无法区分事件时为null并标疑似，不冒充唯一事件号。")
    occurred_at: _datetime = Field(..., description="带时区的交易时间，按Asia/Shanghai归属日期月份；草稿未知可为null。")
    amount_fen: StrictInt = Field(..., ge=1, description="CNY整数分，不是浮点元；草稿可未知，确认必须为正整数。")
    currency: Literal["CNY"] = Field(..., description="初赛只接受CNY，不自动换汇。")
    flow_type: FlowType = Field(..., description="收入、支出、退款、内部转账、还款；草稿可未知，确认前必须明确。")
    merchant: str = Field(..., max_length=500, description="商户原始展示名称；建立个人规则要求非空。")
    description: str = Field(..., max_length=2000, description="交易说明，空说明用空字符串。")
    category: Category = Field(..., description="固定类别代码；pending可作为未分类桶，但建立个人规则不接受pending。")
    id: str = Field(..., description="服务端资源标识，前端原样使用，不自行拼接。")
    version: int = Field(..., ge=1, description="资源当前版本。写操作通过 expected_version 防止覆盖新修改。")
    source: Source = Field(..., description="账单所属支付平台，与采集方式分开。")
    ingestion_method: IngestionMethod = Field(..., description="file为导出文件，screenshot为账单截图。")
    import_batch_id: str = Field(..., description="交易来源批次ID。")
    classification_source: ClassificationSource = Field(..., description="实际分类来源，不得将规则或测试替身标成deepseek。")
    classification_reason: str = Field(..., description="供用户查看的简短分类依据，不是准确率或概率。")
    status: Literal["confirmed"] = Field(..., description="BatchStatus为批次状态；交易status为confirmed，草稿不进入报表。")

class Progress(BaseModel):
    """共享模型 Progress；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    current: int = Field(..., ge=0, description="已处理的候选行数。")
    total: Optional[int] = Field(..., ge=0, description="列表中为筛选后的总数；Progress中为候选行总数，可未知。")

class Batch(BaseModel):
    """共享模型 Batch；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="服务端资源标识，前端原样使用，不自行拼接。")
    version: int = Field(..., ge=1, description="资源当前版本。写操作通过 expected_version 防止覆盖新修改。")
    source: Source = Field(..., description="账单所属支付平台，与采集方式分开。")
    ingestion_method: IngestionMethod = Field(..., description="file为导出文件，screenshot为账单截图。")
    status: BatchStatus = Field(..., description="BatchStatus为批次状态；交易status为confirmed，草稿不进入报表。")
    rows: list[TransactionDraft] = Field(..., description="草稿或本次选中的确认行；处理中的批次可为空数组。")
    issues: list[Issue] = Field(..., description="解析、识别或分类的字段问题；空数组表示暂无问题。")
    progress: Progress = Field(..., description="处理进度，仅供展示，不决定是否可确认。")
    file_name: str = Field(..., description="经过鉴权后展示的原文件名，不能当作服务器磁盘路径。")
    created_at: _datetime = Field(..., description="资源创建时间，带时区ISO 8601。")
    updated_at: _datetime = Field(..., description="最后状态更新时间，带时区ISO 8601。")

class ConfirmRow(BaseModel):
    """共享模型 ConfirmRow；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    row_id: str = Field(..., description="本批次内稳定的草稿行标识，确认和分类按它关联，不能依赖数组顺序。")
    transaction: TransactionInput = Field(..., description="该行最终入账字段，后端重新校验。")
    allow_suspected_duplicate: bool = Field(default=False, description="仅用户明确确认疑似重复仍为新交易时设true。")

class ConfirmInput(BaseModel):
    """共享模型 ConfirmInput；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(..., description="确认操作的UUID。同一次网络重试复用同一ID和请求体。")
    expected_version: int = Field(..., ge=1, description="提交编辑前最后读取的资源版本，冲突返回409和最新版本。")
    rows: list[ConfirmRow] = Field(..., min_length=1, max_length=500, description="草稿或本次选中的确认行；处理中的批次可为空数组。")

class ConfirmResult(BaseModel):
    """共享模型 ConfirmResult；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(..., description="本次确认对应的批次。")
    created_count: int = Field(..., ge=0, description="本次真正新增的交易数。")
    duplicate_count: int = Field(..., ge=0, description="本次提交选中行里被明确判重而跳过的行数。")
    ignored_count: int = Field(..., ge=0, description="该批次草稿中未在本次确认请求提交的行数。")
    transaction_ids: list[str] = Field(..., description="本次新增交易ID；重放确认返回相同数组。")

class RetryInput(BaseModel):
    """共享模型 RetryInput；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(..., ge=1, description="提交编辑前最后读取的资源版本，冲突返回409和最新版本。")

class ResolveMissingInput(BaseModel):
    """共享模型 ResolveMissingInput；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(..., ge=1, description="提交编辑前最后读取的资源版本，冲突返回409和最新版本。")
    default_year: Optional[int] = Field(default=None, ge=2000, le=2100, description="快捷确认的默认年份（如2026）；配合截图月日时间自动补全。")
    instruction: Optional[str] = Field(default=None, max_length=2000, description="用户的自然语言补充说明，交由DeepSeek智能体逐行核对补全。")

class TransactionPatchChanges(BaseModel):
    """需要修改的字段；未提交字段保持原值。显式null只允许在契约可空字段。"""
    model_config = ConfigDict(extra="forbid")

    source_transaction_id: Optional[str] = Field(default=None)
    occurred_at: Optional[_datetime] = Field(default=None)
    amount_fen: Optional[StrictInt] = Field(default=None, ge=1)
    currency: Optional[Literal["CNY"]] = Field(default=None)
    flow_type: Optional[FlowType] = Field(default=None)
    merchant: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = Field(default=None, max_length=2000)
    category: Optional[Category] = Field(default=None)

class TransactionPatch(BaseModel):
    """共享模型 TransactionPatch；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(..., ge=1, description="提交编辑前最后读取的资源版本，冲突返回409和最新版本。")
    changes: TransactionPatchChanges = Field(..., description="需要修改的字段；未提交字段保持原值。显式null只允许在契约可空字段。")
    remember_rule: Optional[bool] = Field(default=False, description="true时同时建立或更新个人商户分类规则，默认false。")

class TransactionPage(BaseModel):
    """共享模型 TransactionPage；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    items: list[Transaction] = Field(..., description="当前列表项，空结果用空数组。")
    total: int = Field(..., ge=0, description="列表中为筛选后的总数；Progress中为候选行总数，可未知。")
    page: int = Field(..., ge=1, description="页码从1开始，默认1。")
    page_size: int = Field(..., ge=1, description="每页默认50，范围1至100。")

class ResolvedCategory(str, Enum):
    """用于个人规则和预算的明确类别，不接受pending。"""

    dining = "dining"
    transport = "transport"
    shopping = "shopping"
    salary = "salary"
    housing = "housing"
    entertainment = "entertainment"
    health = "health"
    education = "education"
    other = "other"

class ClassificationRule(BaseModel):
    """共享模型 ClassificationRule；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="服务端资源标识，前端原样使用，不自行拼接。")
    version: int = Field(..., ge=1, description="资源当前版本。写操作通过 expected_version 防止覆盖新修改。")
    source: Source = Field(..., description="账单所属支付平台，与采集方式分开。")
    merchant_normalized: str = Field(..., min_length=1, description="按本项目标准化步骤得到的精确匹配键，仅对本人和该平台有效。")
    category: ResolvedCategory = Field(..., description="明确的类别代码，不接受pending。")
    enabled: bool = Field(..., description="个人规则是否启用，停用仅影响后续自动分类。")

class RuleList(BaseModel):
    """共享模型 RuleList；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    items: list[ClassificationRule] = Field(..., description="当前列表项，空结果用空数组。")

class RulePatch(BaseModel):
    """共享模型 RulePatch；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(..., ge=1, description="提交编辑前最后读取的资源版本，冲突返回409和最新版本。")
    enabled: Optional[bool] = Field(default=None, description="个人规则是否启用，停用仅影响后续自动分类。")
    category: Optional[ResolvedCategory] = Field(default=None, description="明确的类别代码，不接受pending。")

class BudgetInput(BaseModel):
    """共享模型 BudgetInput；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    month: str = Field(..., pattern="^\\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM，接口不静默默认当前月份。")
    category: ResolvedCategory = Field(..., description="明确的类别代码，不接受pending。")
    amount_fen: StrictInt = Field(..., ge=0, description="分类月预算，非负整数分；与交易金额的正整数要求不同。")

class Budget(BaseModel):
    """共享模型 Budget；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="服务端资源标识，前端原样使用，不自行拼接。")
    month: str = Field(..., pattern="^\\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM，接口不静默默认当前月份。")
    category: ResolvedCategory = Field(..., description="明确的类别代码，不接受pending。")
    amount_fen: StrictInt = Field(..., ge=0, description="保存后的分类月预算，非负整数分。")

class BudgetStatus(BaseModel):
    """共享模型 BudgetStatus；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    category: ResolvedCategory = Field(..., description="明确的类别代码，不接受pending。")
    budget_fen: StrictInt = Field(..., ge=0, description="该类别当月预算，非负整数分。")
    spent_fen: StrictInt = Field(..., description="类别当月净支出，退款跨月时可以为负。")
    remaining_fen: StrictInt = Field(..., description="预算减当月净支出，可以为负。")
    over_fen: StrictInt = Field(..., ge=0, description="max(0,净支出减预算)。")

class Totals(BaseModel):
    """共享模型 Totals；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    income_fen: StrictInt = Field(..., ge=0, description="当月收入，不含退款和内部转账。")
    gross_expense_fen: StrictInt = Field(..., ge=0, description="当月毛支出，不含内部转账和还款。")
    refund_fen: StrictInt = Field(..., ge=0, description="按退款实际发生月计入的退款。")
    net_expense_fen: StrictInt = Field(..., description="毛支出减退款，可以为负。")
    balance_fen: StrictInt = Field(..., description="本期收支差额=收入减毛支出加退款，不是账户余额。")

class MonthlyReportExpenseByCategoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Category = Field(...)
    amount_fen: StrictInt = Field(..., ge=0)

class MonthlyReportDailyTrendItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: _date = Field(...)
    income_fen: StrictInt = Field(..., ge=0)
    gross_expense_fen: StrictInt = Field(..., ge=0)
    refund_fen: StrictInt = Field(..., ge=0)
    net_expense_fen: StrictInt = Field(...)

class MonthlyReport(BaseModel):
    """共享模型 MonthlyReport；HTTP请求与响应均遵守本定义。"""
    model_config = ConfigDict(extra="forbid")

    month: str = Field(..., pattern="^\\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM，接口不静默默认当前月份。")
    totals: Totals = Field(..., description="统一口径汇总，前端不重新做另一套计算。")
    expense_by_category: list[MonthlyReportExpenseByCategoryItem] = Field(..., description="分类毛支出构成，仅返回毛支出大于0的类别；用于饼图。")
    daily_trend: list[MonthlyReportDailyTrendItem] = Field(..., description="该月每个自然日按日期升序返回，无交易日各项为0。")
    budgets: list[BudgetStatus] = Field(..., description="该月已设置预算的类别，按类别代码稳定排序。")

# 兜底：确保跨模型引用在运行时完成解析
_MODELS = (
    FieldError,
    ErrorDetails,
    ErrorError,
    Error,
    User,
    LoginInput,
    Session,
    Issue,
    TransactionInput,
    TransactionDraft,
    ParseResult,
    ClassificationResult,
    Transaction,
    Progress,
    Batch,
    ConfirmRow,
    ConfirmInput,
    ConfirmResult,
    RetryInput,
    ResolveMissingInput,
    TransactionPatchChanges,
    TransactionPatch,
    TransactionPage,
    ClassificationRule,
    RuleList,
    RulePatch,
    BudgetInput,
    Budget,
    BudgetStatus,
    Totals,
    MonthlyReportExpenseByCategoryItem,
    MonthlyReportDailyTrendItem,
    MonthlyReport,
)
for _model in _MODELS:
    _model.model_rebuild()
