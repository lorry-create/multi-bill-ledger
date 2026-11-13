"""DeepSeek 智能分类 + 离线 OCR 截图解析实现（T01 / T04 / T06）。

启用方式（.env 或环境变量）：
    INTELLIGENCE_PROVIDER=app.intelligence.deepseek:DeepSeekIntelligence
    DEEPSEEK_API_KEY=...
    DEEPSEEK_BASE_URL=https://api.deepseek.com   # 可选
    DEEPSEEK_MODEL=deepseek-chat                 # 可选

设计纪律（docs/02、docs/05、docs/13、docs/20）：
1. 分类顺序固定：个人规则（user_rule）> 通用规则（general_rule）> DeepSeek（deepseek）> pending。
2. DeepSeek 只收到脱敏后的最小字段（row_id、商户、商品说明、收支方向、金额分），不传交易单号或用户信息。
3. 严格执行 20s 超时、最多 1 次重试、最多 2 个并发批处理；超时或输出非法时只将受影响行退回 pending 并附 Issue，
   绝不伪造 `deepseek` 或 `general_rule` 来源。
4. 截图通过本地离线 RapidOCR 提取文字；若已配置 DeepSeek Key，辅助做字段结构化并经确定性校验（缺年份绝不猜）。
"""

from __future__ import annotations

import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from ..contracts import (
    Category,
    ClassificationResult,
    ClassificationRule,
    ClassificationSource,
    Issue,
    ParseResult,
    ResolvedCategory,
    TransactionDraft,
)
from .base import (
    ISSUE_CATEGORY_UNCERTAIN,
    MODEL_OUTPUT_INVALID,
    MODEL_TIMEOUT,
    OCR_UNAVAILABLE,
    IntelligenceFailure,
    assert_one_result_per_row,
)
from .fallback import FallbackIntelligence
from .normalize import normalize_merchant
from .ocr import OcrEngine, RapidOcrEngine, extract_bill_from_image
from .resolve import resolve_missing_deterministic, resolve_missing_with_llm
from .rules import classify_by_keywords

logger = logging.getLogger("app.intelligence.deepseek")

_DEFAULT_BASE_URL = "https://api.deepseek.com"
_DEFAULT_MODEL = "deepseek-chat"
_CALL_TIMEOUT_SECONDS = 20.0
_MAX_ATTEMPTS = 2
_MAX_CONCURRENCY = 2
_BATCH_SIZE = 20

_RESOLVED_CATEGORY_SET = {item.value for item in ResolvedCategory}
_ALLOWED_LLM_CATEGORIES = _RESOLVED_CATEGORY_SET | {Category.pending.value}

# (status_code, body_dict)
HttpTransport = Callable[[str, dict[str, str], dict[str, Any], float], tuple[int, dict[str, Any]]]


def _default_transport(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> tuple[int, dict[str, Any]]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            err_body = json.loads(raw)
        except ValueError:
            err_body = {}
        return exc.code, err_body
    except (TimeoutError, socket.timeout) as exc:
        raise TimeoutError("request timed out") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise TimeoutError("request timed out") from exc
        raise ConnectionError("network request failed") from exc


def _strip_json_fence(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
    return cleaned.strip()


class DeepSeekIntelligence:
    """结合离线 OCR、规则引擎与 DeepSeek API 的完整智能模块实现。"""

    name = "deepseek"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float = _CALL_TIMEOUT_SECONDS,
        batch_size: int = _BATCH_SIZE,
        ocr_engine: OcrEngine | None = None,
        transport: HttpTransport | None = None,
    ) -> None:
        self.api_key = (
            os.environ.get("DEEPSEEK_API_KEY", "") if api_key is None else api_key
        ).strip()
        raw_url = (
            os.environ.get("DEEPSEEK_BASE_URL", _DEFAULT_BASE_URL)
            if base_url is None
            else base_url
        ).strip()
        self.base_url = (raw_url or _DEFAULT_BASE_URL).rstrip("/")
        raw_model = (
            os.environ.get("DEEPSEEK_MODEL", _DEFAULT_MODEL) if model is None else model
        ).strip()
        self.model = raw_model or _DEFAULT_MODEL
        self.timeout_seconds = timeout_seconds
        self.batch_size = max(1, batch_size)
        self._fallback = FallbackIntelligence()
        self._ocr_engine: OcrEngine = ocr_engine or RapidOcrEngine()
        self._transport: HttpTransport = transport or _default_transport
        self.last_usage_stats: dict[str, Any] = {}

    # ---- 文件解析（T01） ----

    def parse_bill_file(self, data: bytes, filename: str, source: str) -> ParseResult:
        return self._fallback.parse_bill_file(data, filename, source)

    # ---- 截图识别（T06） ----

    def recognize_bill_image(
        self, data: bytes, mime_type: str, source: str
    ) -> ParseResult:
        if mime_type and mime_type not in ("image/png", "image/jpeg"):
            raise IntelligenceFailure(OCR_UNAVAILABLE, f"不支持的截图格式：{mime_type}")
        structurer = self._structure_ocr_rows if self.api_key else None
        return extract_bill_from_image(
            data,
            source,
            ocr_engine=self._ocr_engine,
            llm_structurer=structurer,
        )

    def _structure_ocr_rows(self, visual_rows: list[str], source: str) -> str:
        """可选使用 DeepSeek 把 OCR 行文本结构化为 JSON，仍经 ocr.py 严格校验。"""
        system_prompt = (
            "你是个人账单结构化助手。下面是从支付截图离线 OCR 识别出的按行文本。"
            "请提取每笔交易并返回严格 JSON：{\"items\": [{\"occurred_at_raw\": \"\", "
            "\"amount_raw\": \"\", \"flow_type\": \"expense|income|refund|transfer|repayment|null\", "
            "\"merchant\": \"\", \"description\": \"\", \"source_transaction_id\": null, \"status\": \"\"}]}。"
            "注意：如果原图时间没有年份（例如只有 11-08 12:30 或 今天 12:30），occurred_at_raw 必须原样保留，"
            "严禁自己补全或猜测年份；金额保留原始正负号和两位小数。"
        )
        user_payload = json.dumps(
            {"source": source, "ocr_lines": visual_rows}, ensure_ascii=False
        )
        content, _usage, _elapsed = self._call_chat_json(system_prompt, user_payload)
        return content

    # ---- 商户标准化 ----

    def normalize_merchant(self, raw: str) -> str:
        return normalize_merchant(raw)

    # ---- 三层分类（T04） ----

    def classify_transactions(
        self,
        rows: list[TransactionDraft],
        rules: list[ClassificationRule],
        use_llm: bool = False,
    ) -> list[ClassificationResult]:
        """优先级：本人规则 > 通用规则 > DeepSeek（仅 use_llm=True 且配好 Key）> pending。"""
        by_merchant: dict[str, ClassificationRule] = {}
        for rule in rules:
            if rule.enabled and rule.source is not None:
                by_merchant.setdefault(rule.merchant_normalized, rule)

        resolved: dict[str, ClassificationResult] = {}
        unmatched: list[TransactionDraft] = []

        for row in rows:
            hit = by_merchant.get(normalize_merchant(row.merchant))
            if hit is not None:
                resolved[row.row_id] = ClassificationResult(
                    row_id=row.row_id,
                    category=hit.category,
                    classification_source=ClassificationSource.user_rule,
                    classification_reason=f"命中本人规则（{hit.merchant_normalized}）",
                    issues=[],
                )
                continue

            matched = classify_by_keywords(row.merchant, row.description, row.flow_type)
            if matched is not None:
                category, reason = matched
                resolved[row.row_id] = ClassificationResult(
                    row_id=row.row_id,
                    category=category,
                    classification_source=ClassificationSource.general_rule,
                    classification_reason=reason,
                    issues=[],
                )
                continue

            unmatched.append(row)

        if unmatched:
            if use_llm and self.api_key:
                llm_results = self._classify_unmatched_with_llm(unmatched)
                for item in llm_results:
                    resolved[item.row_id] = item
            else:
                reason = (
                    "通用规则未命中，未启用模型分类"
                    if not use_llm
                    else "通用规则未命中，未配置 DeepSeek API Key"
                )
                for row in unmatched:
                    resolved[row.row_id] = self._pending_result(
                        row.row_id,
                        code=ISSUE_CATEGORY_UNCERTAIN,
                        reason=reason,
                        issue_message="无法自动判断类别，请手动选择",
                    )

        ordered = [resolved[row.row_id] for row in rows]
        assert_one_result_per_row(rows, ordered)
        return ordered

    def _classify_unmatched_with_llm(
        self, rows: list[TransactionDraft]
    ) -> list[ClassificationResult]:
        batches = [
            rows[i : i + self.batch_size]
            for i in range(0, len(rows), self.batch_size)
        ]

        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_tokens = 0
        total_elapsed_ms = 0
        out_by_row: dict[str, ClassificationResult] = {}

        def _run_batch(batch: list[TransactionDraft]) -> tuple[dict[str, ClassificationResult], dict[str, int], int]:
            return self._classify_single_batch(batch)

        if len(batches) == 1:
            batch_res, usage, elapsed_ms = _run_batch(batches[0])
            out_by_row.update(batch_res)
            total_prompt_tokens += usage.get("prompt_tokens", 0)
            total_completion_tokens += usage.get("completion_tokens", 0)
            total_tokens += usage.get("total_tokens", 0)
            total_elapsed_ms += elapsed_ms
        else:
            with ThreadPoolExecutor(max_workers=min(_MAX_CONCURRENCY, len(batches))) as pool:
                for batch_res, usage, elapsed_ms in pool.map(_run_batch, batches):
                    out_by_row.update(batch_res)
                    total_prompt_tokens += usage.get("prompt_tokens", 0)
                    total_completion_tokens += usage.get("completion_tokens", 0)
                    total_tokens += usage.get("total_tokens", 0)
                    total_elapsed_ms += elapsed_ms

        self.last_usage_stats = {
            "model": self.model,
            "batches": len(batches),
            "rows": len(rows),
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
            "elapsed_ms": total_elapsed_ms,
        }
        logger.info(
            "DeepSeek 分类完成 model=%s batches=%d rows=%d total_tokens=%d elapsed_ms=%d",
            self.model,
            len(batches),
            len(rows),
            total_tokens,
            total_elapsed_ms,
        )
        return [out_by_row[row.row_id] for row in rows]

    def _classify_single_batch(
        self, batch: list[TransactionDraft]
    ) -> tuple[dict[str, ClassificationResult], dict[str, int], int]:
        # 只送最小脱敏字段：不包含交易单号、时间或用户身份
        sanitized_rows = [
            {
                "row_id": row.row_id,
                "merchant": row.merchant[:80],
                "description": row.description[:120],
                "flow_type": row.flow_type.value if row.flow_type else None,
                "amount_fen": row.amount_fen,
            }
            for row in batch
        ]
        system_prompt = (
            "你是个人账单分类助手。请对输入的每条交易进行消费/收入分类，只能从以下类别中选一个：\n"
            "dining（餐饮）、transport（交通）、shopping（购物）、salary（工资）、housing（居住）、"
            "entertainment（娱乐）、health（医疗）、education（教育）、other（其他）、pending（确实无法判断）。\n"
            "必须返回严格 JSON：{\"items\": [{\"row_id\": \"...\", \"category\": \"...\", \"reason\": \"简短理由\"}]}。\n"
            "要求：每条输入 row_id 都必须原样返回，禁止修改或遗漏 row_id；无法确定请返回 pending。"
        )
        user_payload = json.dumps({"transactions": sanitized_rows}, ensure_ascii=False)

        try:
            content, usage, elapsed_ms = self._call_chat_json(system_prompt, user_payload)
        except IntelligenceFailure as exc:
            # 文档要求：模型超时或输出无效时，受影响交易退回 pending 并附对应 Issue，绝不编造成功
            fallback_map = {
                row.row_id: self._pending_result(
                    row.row_id,
                    code=exc.code,
                    reason=exc.message,
                    issue_message=exc.message,
                )
                for row in batch
            }
            return fallback_map, {}, 0

        parsed_map = self._parse_llm_classification_json(content, batch)
        return parsed_map, usage, elapsed_ms

    def _parse_llm_classification_json(
        self, raw_content: str, batch: list[TransactionDraft]
    ) -> dict[str, ClassificationResult]:
        want_ids = {row.row_id for row in batch}
        try:
            payload = json.loads(_strip_json_fence(raw_content))
        except ValueError:
            return {
                row.row_id: self._pending_result(
                    row.row_id,
                    code=MODEL_OUTPUT_INVALID,
                    reason="智能分类返回非 JSON 格式，已退回待确认",
                    issue_message="智能分类返回结果不符合约定格式",
                )
                for row in batch
            }

        raw_items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(raw_items, list):
            return {
                row.row_id: self._pending_result(
                    row.row_id,
                    code=MODEL_OUTPUT_INVALID,
                    reason="智能分类返回缺少 items 列表，已退回待确认",
                    issue_message="智能分类返回结果不符合约定格式",
                )
                for row in batch
            }

        # 统计 row_id 出现次数：重复 row_id 一律判无效，绝不按位置或随机取一条错配
        counts: dict[str, int] = {}
        entries_by_id: dict[str, dict[str, Any]] = {}
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            rid = str(item.get("row_id") or "").strip()
            if rid not in want_ids:
                continue
            counts[rid] = counts.get(rid, 0) + 1
            entries_by_id[rid] = item

        results: dict[str, ClassificationResult] = {}
        for row in batch:
            rid = row.row_id
            if counts.get(rid, 0) != 1:
                results[rid] = self._pending_result(
                    rid,
                    code=MODEL_OUTPUT_INVALID,
                    reason="模型未返回唯一的 row_id，已退回待确认",
                    issue_message="智能分类未能匹配该笔记录，请手动选择类别",
                )
                continue

            entry = entries_by_id[rid]
            cat_raw = str(entry.get("category") or "").strip()
            reason_raw = str(entry.get("reason") or "").strip()

            if cat_raw not in _ALLOWED_LLM_CATEGORIES or cat_raw == Category.pending.value:
                results[rid] = self._pending_result(
                    rid,
                    code=ISSUE_CATEGORY_UNCERTAIN,
                    reason=reason_raw or "模型无法确定类别，请手动选择",
                    issue_message="无法自动判断类别，请手动选择",
                )
                continue

            results[rid] = ClassificationResult(
                row_id=rid,
                category=Category(cat_raw),
                classification_source=ClassificationSource.deepseek,
                classification_reason=reason_raw[:120] or f"DeepSeek 分类为 {cat_raw}",
                issues=[],
            )
        return results

    def _call_chat_json(
        self, system_prompt: str, user_content: str
    ) -> tuple[str, dict[str, int], int]:
        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }

        last_exc: IntelligenceFailure | None = None
        start = time.monotonic()
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                status, data = self._transport(url, headers, payload, self.timeout_seconds)
            except TimeoutError:
                last_exc = IntelligenceFailure(MODEL_TIMEOUT, "智能分类服务响应超时")
                continue
            except Exception:
                last_exc = IntelligenceFailure(MODEL_OUTPUT_INVALID, "智能分类服务请求失败")
                continue

            if status == 408 or status == 504:
                last_exc = IntelligenceFailure(MODEL_TIMEOUT, "智能分类服务响应超时")
                continue
            if status == 429 or status >= 500:
                last_exc = IntelligenceFailure(MODEL_OUTPUT_INVALID, "智能分类服务暂时不可用")
                continue
            if status != 200:
                raise IntelligenceFailure(
                    MODEL_OUTPUT_INVALID, f"智能分类服务返回错误状态码（{status}）"
                )

            try:
                content = str(data["choices"][0]["message"]["content"])
                json.loads(_strip_json_fence(content))
            except (KeyError, IndexError, TypeError, ValueError):
                last_exc = IntelligenceFailure(
                    MODEL_OUTPUT_INVALID, "智能分类返回结果不符合约定格式"
                )
                continue

            usage_raw = data.get("usage") if isinstance(data, dict) else None
            usage = {
                "prompt_tokens": int((usage_raw or {}).get("prompt_tokens") or 0),
                "completion_tokens": int((usage_raw or {}).get("completion_tokens") or 0),
                "total_tokens": int((usage_raw or {}).get("total_tokens") or 0),
            }
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return content, usage, elapsed_ms

        assert last_exc is not None
        raise last_exc

    @staticmethod
    def _pending_result(
        row_id: str, *, code: str, reason: str, issue_message: str
    ) -> ClassificationResult:
        return ClassificationResult(
            row_id=row_id,
            category=Category.pending,
            classification_source=ClassificationSource.pending,
            classification_reason=reason[:120],
            issues=[
                Issue(
                    row_id=row_id,
                    field="category",
                    code=code,
                    message=issue_message,
                )
            ],
        )

    def resolve_missing_fields(
        self,
        rows: list[TransactionDraft],
        *,
        default_year: int | None = None,
        instruction: str | None = None,
    ) -> list[TransactionDraft]:
        """结合快捷年份或 DeepSeek 对话解析用户说明，按 row_id 精准补全缺失字段。"""
        if not self.api_key:
            return resolve_missing_deterministic(
                rows, default_year=default_year, instruction=instruction
            )
        return resolve_missing_with_llm(
            rows,
            default_year=default_year,
            instruction=instruction,
            chat_json_fn=lambda msgs, _timeout: self._call_chat_json(
                msgs[0]["content"], msgs[1]["content"]
            )[0],
            timeout_seconds=int(self.timeout_seconds),
        )

