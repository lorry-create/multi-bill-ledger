"""交互式缺失字段补充：确定性解析 + DeepSeek 自然语言逐行补全。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from ..contracts import (
    Category,
    ClassificationSource,
    FlowType,
    Issue,
    TransactionDraft,
)
from .base import (
    ISSUE_CATEGORY_UNCERTAIN,
    ISSUE_FLOW_TYPE_UNKNOWN,
    ISSUE_INVALID_TIME,
    ISSUE_TIME_MISSING,
    MODEL_OUTPUT_INVALID,
    IntelligenceFailure,
)

CST = timezone(timedelta(hours=8))

_MISSING_YEAR_HINT_RE = re.compile(r"截图时间缺少具体年份[（(]([^）)]+)[）)]")
_STANDALONE_YEAR_RE = re.compile(
    r"^(?:全部|所有|都是|均为|统一|按|默认)?\s*(20\d{2})\s*年?(?:度|吧|哦|哈|的)?\s*[。.!！]?$"
)
_FULL_DT_RE = re.compile(
    r"(20\d{2})\s*[年/\-.]\s*(\d{1,2})\s*[月/\-.]\s*(\d{1,2})\s*日?"
    r"(?:[T\s]*(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?"
)
_PARTIAL_MD_RE = re.compile(
    r"(\d{1,2})\s*[月/\-.]\s*(\d{1,2})\s*日?"
    r"(?:\s*(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?"
)
_YEAR_RE = re.compile(r"(?<!\d)(20\d{2})(?!\d)\s*年?")
_CLAUSE_SPLIT_RE = re.compile(r"[,，;；。\n]+")

_CATEGORY_ALIASES: tuple[tuple[Category, tuple[str, ...]], ...] = (
    (Category.dining, ("餐饮", "美食", "吃饭", "外卖", "零食", "coffee", "dining")),
    (Category.transport, ("交通", "出行", "打车", "地铁", "公交", "高铁", "加油", "transport")),
    (Category.shopping, ("购物", "网购", "日用", "百货", "淘宝", "京东", "shopping")),
    (Category.salary, ("工资", "薪资", "奖金", "薪水", "salary")),
    (Category.housing, ("居住", "住房", "房租", "水电", "物业", "宽带", "话费", "housing")),
    (Category.entertainment, ("娱乐", "电影", "游戏", "会员", "影音", "旅游", "entertainment")),
    (Category.health, ("医疗", "医药", "看病", "挂号", "体检", "医院", "health")),
    (Category.education, ("教育", "学习", "课程", "学费", "书籍", "考试", "education")),
    (Category.other, ("其他", "其它", "杂项", "人情", "红包", "other")),
)

_FLOW_ALIASES: tuple[tuple[FlowType, tuple[str, ...]], ...] = (
    (FlowType.income, ("收入", "收款", "income")),
    (FlowType.expense, ("支出", "消费", "付款", "expense")),
    (FlowType.refund, ("退款", "退货", "refund")),
    (FlowType.transfer, ("转账", "内部转账", "transfer")),
    (FlowType.repayment, ("还款", "信用卡还款", "repayment")),
)

_RESOLVE_SYSTEM_PROMPT = (
    "你是个人账单核对助手。用户上传账单截图后，部分交易缺少具体年份、完整日期或类别。"
    "现在你会收到交易草稿列表（含 1-based 序号 index、唯一 row_id、已识别部分时间 partial_time_hint、"
    "金额 amount_yuan、收支方向 flow_type、商户 merchant、当前类别 category、缺失问题 issues），"
    "以及用户的默认年份 default_year 和自然语言补充说明 instruction。\n\n"
    "请严格遵守以下规则，只输出合法 JSON 对象：\n"
    "1. 输出格式：{\"updates\": [{\"row_id\": \"...\", \"occurred_at\": \"YYYY-MM-DDTHH:MM:SS+08:00\" | null, "
    "\"category\": \"枚举值或null\", \"flow_type\": \"枚举值或null\", \"reason\": \"简短说明\"}]}\n"
    "2. 保留输入中的每个需要更新的 row_id，不得修改或编造 row_id。\n"
    "3. 补全时间时使用 Asia/Shanghai 时区（+08:00）：\n"
    "   - 若某行有 partial_time_hint（例如 \"11月6日16:53\"）且用户指定/确认了年份（如 2026），"
    "则保留原月、日、时、分，组合为 \"2026-11-06T16:53:00+08:00\"。\n"
    "   - 若某行没有 partial_time_hint 且用户在 instruction 中给出了日期（如 \"第8笔是2026年11月1日\"），"
    "没有具体时分时可设为 00:00:00+08:00；若有具体时间则按用户所说填写。\n"
    "   - 绝不允许为用户既没确认、也没有 partial_time_hint 的行虚构月日或年份；无法确定的行 occurred_at 填 null。\n"
    "4. 仅当用户在 instruction 中要求修改或指定某行类别/收支方向时，才填写 category / flow_type，否则填 null：\n"
    "   - category 合法值仅限：dining, transport, shopping, salary, housing, entertainment, health, education, other\n"
    "   - flow_type 合法值仅限：income, expense, refund, transfer, repayment\n"
    "5. 若某行无需修改，可省略或全部字段填 null。"
)


def extract_missing_year_hint(issues: list[Issue]) -> str | None:
    """从 TIME_MISSING 提示文本中提取缺少具体年份的局部月日时间。"""
    for issue in issues:
        if issue.code != ISSUE_TIME_MISSING:
            continue
        matched = _MISSING_YEAR_HINT_RE.search(issue.message or "")
        if matched:
            hint = matched.group(1).strip()
            if hint:
                return hint
    return None


def _build_cst_datetime(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
) -> datetime | None:
    if not (2000 <= year <= 2100):
        return None
    try:
        return datetime(year, month, day, hour, minute, second, tzinfo=CST)
    except ValueError:
        return None


def combine_year_with_partial_datetime(raw_partial: str, year: int) -> datetime | None:
    """将用户确认的年份与截图识别的局部月日时间拼接为带时区 datetime。"""
    text = (raw_partial or "").strip()
    if not text:
        return None

    full_match = _FULL_DT_RE.search(text)
    if full_match and int(full_match.group(1)) == year:
        return _build_cst_datetime(
            int(full_match.group(1)),
            int(full_match.group(2)),
            int(full_match.group(3)),
            int(full_match.group(4) or 0),
            int(full_match.group(5) or 0),
            int(full_match.group(6) or 0),
        )

    matched = _PARTIAL_MD_RE.search(text)
    if not matched:
        return None
    return _build_cst_datetime(
        year,
        int(matched.group(1)),
        int(matched.group(2)),
        int(matched.group(3) or 0),
        int(matched.group(4) or 0),
        int(matched.group(5) or 0),
    )


def parse_resolved_datetime(raw: Any) -> datetime | None:
    """解析补全后的完整日期时间字符串并统一转为 Asia/Shanghai (+08:00)。"""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None

    iso_candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(iso_candidate)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=CST)
        else:
            parsed = parsed.astimezone(CST)
        if 2000 <= parsed.year <= 2100:
            return parsed
        return None
    except ValueError:
        pass

    matched = _FULL_DT_RE.fullmatch(text)
    if not matched:
        return None
    return _build_cst_datetime(
        int(matched.group(1)),
        int(matched.group(2)),
        int(matched.group(3)),
        int(matched.group(4) or 0),
        int(matched.group(5) or 0),
        int(matched.group(6) or 0),
    )


def is_simple_year_only(default_year: int | None, instruction: str | None) -> int | None:
    """判断用户输入是否等价于纯单一确认年份（无复杂多行自然语言约束）。"""
    text = (instruction or "").strip()
    if not text:
        return default_year
    matched = _STANDALONE_YEAR_RE.match(text)
    if not matched:
        return None
    parsed_year = int(matched.group(1))
    if not (2000 <= parsed_year <= 2100):
        return None
    if default_year is not None and default_year != parsed_year:
        return None
    return parsed_year


def _parse_category_value(raw: Any) -> Category | None:
    if not isinstance(raw, str):
        return None
    val = raw.strip().lower()
    for member in Category:
        if member != Category.pending and val == member.value:
            return member
    return None


def _parse_flow_type_value(raw: Any) -> FlowType | None:
    if not isinstance(raw, str):
        return None
    val = raw.strip().lower()
    for member in FlowType:
        if val == member.value:
            return member
    return None


def apply_draft_updates(
    drafts: list[TransactionDraft],
    updates: dict[str, dict[str, Any]],
) -> list[TransactionDraft]:
    """将经过校验的字段更新合入草稿列表，并清除对应已解决的 issue。"""
    resolved: list[TransactionDraft] = []
    for draft in drafts:
        patch = updates.get(draft.row_id)
        if not patch:
            resolved.append(draft)
            continue

        new_fields: dict[str, Any] = {}
        issues = list(draft.issues)

        new_dt = patch.get("occurred_at")
        if isinstance(new_dt, datetime):
            if new_dt.tzinfo is None:
                new_dt = new_dt.replace(tzinfo=CST)
            new_fields["occurred_at"] = new_dt.astimezone(CST)
            issues = [
                item
                for item in issues
                if item.code not in (ISSUE_TIME_MISSING, ISSUE_INVALID_TIME)
                and item.field != "occurred_at"
            ]

        new_cat = patch.get("category")
        if isinstance(new_cat, Category) and new_cat != Category.pending:
            new_fields["category"] = new_cat
            source = patch.get("classification_source")
            if isinstance(source, ClassificationSource):
                new_fields["classification_source"] = source
            reason = str(patch.get("classification_reason") or "").strip()
            if reason:
                new_fields["classification_reason"] = reason
            issues = [
                item
                for item in issues
                if item.code != ISSUE_CATEGORY_UNCERTAIN and item.field != "category"
            ]

        new_flow = patch.get("flow_type")
        if isinstance(new_flow, FlowType):
            new_fields["flow_type"] = new_flow
            issues = [
                item
                for item in issues
                if item.code != ISSUE_FLOW_TYPE_UNKNOWN and item.field != "flow_type"
            ]

        new_fields["issues"] = issues
        resolved.append(draft.model_copy(update=new_fields))
    return resolved


def _extract_clause_indices(clause: str, total: int, unassigned: list[int]) -> list[int]:
    """从单条中文子句解析目标行索引（0-based）。"""
    matched_front = re.search(r"前\s*(\d+)\s*[笔条行]", clause)
    if matched_front:
        count = min(total, max(0, int(matched_front.group(1))))
        return list(range(count))

    matched_back = re.search(r"(?:后|最后)\s*(\d+)\s*[笔条行]", clause)
    if matched_back:
        count = min(total, max(0, int(matched_back.group(1))))
        return list(range(max(0, total - count), total))

    if "最后一" in clause and total > 0:
        return [total - 1]

    matched_range = re.search(r"第?\s*(\d+)\s*[-~至到]\s*第?\s*(\d+)\s*[笔条行]?", clause)
    if matched_range:
        start = max(1, int(matched_range.group(1)))
        end = min(total, int(matched_range.group(2)))
        if start <= end:
            return [idx - 1 for idx in range(start, end + 1)]

    explicit_nums = re.findall(r"第\s*(\d+)", clause)
    if explicit_nums:
        return [int(n) - 1 for n in explicit_nums if 1 <= int(n) <= total]

    if any(word in clause for word in ("其余", "剩下", "剩余", "其他几笔", "其它几笔")):
        return list(unassigned)

    if any(word in clause for word in ("全部", "所有", "都是", "均为", "统一")):
        return list(range(total))

    return []


def _extract_clause_category(clause: str) -> Category | None:
    if not any(
        cue in clause for cue in ("归", "属于", "算", "分类", "类别", "改成", "改为", "设为")
    ):
        return None
    lowered = clause.lower()
    for category, aliases in _CATEGORY_ALIASES:
        if any(alias in lowered for alias in aliases):
            return category
    return None


def _extract_clause_flow(clause: str) -> FlowType | None:
    if not any(cue in clause for cue in ("方向", "流向", "收支", "改成", "改为", "设为", "归为")):
        return None
    lowered = clause.lower()
    for flow, aliases in _FLOW_ALIASES:
        if any(alias in lowered for alias in aliases):
            return flow
    return None


def resolve_missing_deterministic(
    drafts: list[TransactionDraft],
    *,
    default_year: int | None = None,
    instruction: str | None = None,
) -> list[TransactionDraft]:
    """无需联网模型的确定性补全：支持 default_year 与常见中文按行指令。"""
    total = len(drafts)
    updates: dict[str, dict[str, Any]] = {}
    touched_indices: set[int] = set()

    text = (instruction or "").strip()
    if text:
        simple_year = is_simple_year_only(default_year, text)
        if simple_year is not None:
            default_year = simple_year
        else:
            clauses = [c.strip() for c in _CLAUSE_SPLIT_RE.split(text) if c.strip()]
            for clause in clauses:
                unassigned = [i for i in range(total) if i not in touched_indices]
                target_indices = _extract_clause_indices(clause, total, unassigned)
                if not target_indices and len(clauses) == 1:
                    yr_only = _YEAR_RE.search(clause)
                    if yr_only:
                        target_indices = list(range(total))

                if not target_indices:
                    continue

                full_match = _FULL_DT_RE.search(clause)
                year_match = _YEAR_RE.search(clause)
                clause_year = int(full_match.group(1)) if full_match else (
                    int(year_match.group(1)) if year_match else default_year
                )
                partial_match = None if full_match else _PARTIAL_MD_RE.search(clause)
                clause_cat = _extract_clause_category(clause)
                clause_flow = _extract_clause_flow(clause)

                for idx in target_indices:
                    draft = drafts[idx]
                    patch = updates.setdefault(draft.row_id, {})
                    touched_indices.add(idx)

                    if full_match:
                        dt = _build_cst_datetime(
                            int(full_match.group(1)),
                            int(full_match.group(2)),
                            int(full_match.group(3)),
                            int(full_match.group(4) or 0),
                            int(full_match.group(5) or 0),
                            int(full_match.group(6) or 0),
                        )
                        if dt is not None:
                            patch["occurred_at"] = dt
                    elif partial_match and clause_year is not None:
                        dt = _build_cst_datetime(
                            clause_year,
                            int(partial_match.group(1)),
                            int(partial_match.group(2)),
                            int(partial_match.group(3) or 0),
                            int(partial_match.group(4) or 0),
                            int(partial_match.group(5) or 0),
                        )
                        if dt is not None:
                            patch["occurred_at"] = dt
                    elif clause_year is not None and draft.occurred_at is None:
                        hint = extract_missing_year_hint(draft.issues)
                        if hint:
                            dt = combine_year_with_partial_datetime(hint, clause_year)
                            if dt is not None:
                                patch["occurred_at"] = dt

                    if clause_cat is not None:
                        patch["category"] = clause_cat
                        patch["classification_source"] = ClassificationSource.manual
                        patch["classification_reason"] = "用户补充说明指定分类"
                    if clause_flow is not None:
                        patch["flow_type"] = clause_flow

    if default_year is not None:
        for draft in drafts:
            existing_patch = updates.get(draft.row_id, {})
            if draft.occurred_at is None and "occurred_at" not in existing_patch:
                hint = extract_missing_year_hint(draft.issues)
                if hint:
                    dt = combine_year_with_partial_datetime(hint, default_year)
                    if dt is not None:
                        updates.setdefault(draft.row_id, {})["occurred_at"] = dt

    return apply_draft_updates(drafts, updates)


def sanitize_prompt_text(text: str, limit: int = 160) -> str:
    """脱敏长数字串并限制长度，避免敏感单号/手机号进入提示词。"""
    cleaned = re.sub(r"\d{11,}", "[REDACTED]", (text or "").strip())
    return cleaned[:limit]


def _strip_json_fence(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
    return cleaned.strip()


def resolve_missing_with_llm(
    drafts: list[TransactionDraft],
    *,
    default_year: int | None,
    instruction: str | None,
    chat_json_fn: Callable[[list[dict[str, str]], int], str],
    sanitize_fn: Callable[[str, int], str] = sanitize_prompt_text,
    timeout_seconds: int = 20,
) -> list[TransactionDraft]:
    """优先识别纯年份快捷路径，复杂自然语言说明调用 DeepSeek 解析后严格校验。"""
    simple_year = is_simple_year_only(default_year, instruction)
    if simple_year is not None:
        return resolve_missing_deterministic(drafts, default_year=simple_year)

    rows_payload = [
        {
            "index": idx,
            "row_id": draft.row_id,
            "occurred_at": draft.occurred_at.isoformat() if draft.occurred_at else None,
            "partial_time_hint": extract_missing_year_hint(draft.issues),
            "amount_yuan": (
                f"{draft.amount_fen / 100:.2f}" if draft.amount_fen is not None else None
            ),
            "flow_type": draft.flow_type.value if draft.flow_type else None,
            "merchant": sanitize_fn(draft.merchant or "", 120),
            "description": sanitize_fn(draft.description or "", 160),
            "category": draft.category.value,
            "issues": [issue.code for issue in draft.issues],
        }
        for idx, draft in enumerate(drafts, start=1)
    ]

    user_payload = {
        "default_year": default_year,
        "instruction": sanitize_fn(instruction or "", 1000),
        "rows": rows_payload,
    }
    raw = chat_json_fn(
        [
            {"role": "system", "content": _RESOLVE_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        timeout_seconds,
    )

    try:
        parsed = json.loads(_strip_json_fence(raw))
    except ValueError as exc:
        raise IntelligenceFailure(MODEL_OUTPUT_INVALID, "智能补全返回格式无法解析") from exc

    raw_updates = (
        parsed.get("updates") or parsed.get("items")
        if isinstance(parsed, dict)
        else None
    )
    if not isinstance(raw_updates, list):
        raise IntelligenceFailure(MODEL_OUTPUT_INVALID, "智能补全结果缺少 updates 列表")

    valid_ids = {draft.row_id for draft in drafts}
    updates: dict[str, dict[str, Any]] = {}
    for item in raw_updates:
        if not isinstance(item, dict):
            continue
        row_id = str(item.get("row_id") or "").strip()
        if row_id not in valid_ids:
            continue

        patch: dict[str, Any] = {}
        raw_dt = item.get("occurred_at")
        if raw_dt is not None and str(raw_dt).strip():
            dt = parse_resolved_datetime(str(raw_dt))
            if dt is not None:
                patch["occurred_at"] = dt

        cat = _parse_category_value(item.get("category"))
        if cat is not None:
            patch["category"] = cat
            patch["classification_source"] = ClassificationSource.deepseek
            reason = str(item.get("reason") or "").strip()
            patch["classification_reason"] = (
                f"DeepSeek补充：{reason[:60]}" if reason else "DeepSeek结合用户说明补充分类"
            )

        flow = _parse_flow_type_value(item.get("flow_type"))
        if flow is not None:
            patch["flow_type"] = flow

        if patch:
            updates[row_id] = patch

    # 若用户同时选定了 default_year 且仍有局部时间行未在 LLM 输出中补上，安全兜底组合年份与原月日时分
    if default_year is not None:
        for draft in drafts:
            patch = updates.get(draft.row_id, {})
            if draft.occurred_at is None and "occurred_at" not in patch:
                hint = extract_missing_year_hint(draft.issues)
                if hint:
                    dt = combine_year_with_partial_datetime(hint, default_year)
                    if dt is not None:
                        updates.setdefault(draft.row_id, {})["occurred_at"] = dt

    return apply_draft_updates(drafts, updates)


__all__ = [
    "apply_draft_updates",
    "combine_year_with_partial_datetime",
    "extract_missing_year_hint",
    "is_simple_year_only",
    "parse_resolved_datetime",
    "resolve_missing_deterministic",
    "resolve_missing_with_llm",
    "sanitize_prompt_text",
]
