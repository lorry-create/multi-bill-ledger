"""T01 / T04 / T06 智能模块（DeepSeek 分类 + 离线 RapidOCR 截图解析）测试。

设计约束：
- 全程离线可运行（使用 FakeTransport 与 FakeOcrEngine），不消耗外部 API 配额。
- 同时包含基于本地真实 RapidOCR 的端到端合成截图识别验证（在存在中文字体时运行）。

运行（在 backend/ 目录）：
    python -m unittest tests.test_intelligence_deepseek_ocr -v
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

_TMP_DIR = tempfile.mkdtemp(prefix="mbl_d_test_")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault(
    "DATABASE_URL", f"sqlite+pysqlite:///{Path(_TMP_DIR, 'test.db').as_posix()}"
)
os.environ.setdefault("SESSION_SECRET", "test-session-secret-not-for-production")
os.environ.setdefault("DATA_ENCRYPTION_KEY", "test-data-key-not-for-production")
os.environ.setdefault("COOKIE_SECURE", "0")

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import models  # noqa: E402
from app.contracts import (  # noqa: E402
    BatchStatus,
    Category,
    ClassificationRule,
    ClassificationSource,
    FlowType,
    Issue,
    Source,
    TransactionDraft,
)
from app.db import Base  # noqa: E402
from app.intelligence import (  # noqa: E402
    INVALID_FILE,
    ISSUE_CATEGORY_UNCERTAIN,
    ISSUE_FLOW_TYPE_UNKNOWN,
    ISSUE_MERCHANT_MISSING,
    ISSUE_ROWS_SKIPPED,
    ISSUE_TIME_MISSING,
    MODEL_OUTPUT_INVALID,
    MODEL_TIMEOUT,
    OCR_FIELD_MISSING,
    OCR_UNAVAILABLE,
    DeepSeekIntelligence,
    IntelligenceFailure,
    IntelligenceProvider,
    build_intelligence,
    normalize_merchant,
    resolve_missing_deterministic,
)
from app.intelligence.ocr import OcrLine  # noqa: E402
from app.main import app  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services import imports as import_service  # noqa: E402

CST = timezone(timedelta(hours=8))


def _draft(
    row_id: str,
    merchant: str,
    description: str = "",
    flow: FlowType | None = FlowType.expense,
    order_id: str | None = "ORD-SECRET-123",
) -> TransactionDraft:
    return TransactionDraft(
        source_transaction_id=order_id,
        occurred_at=datetime(2026, 11, 10, 12, 0, tzinfo=CST),
        amount_fen=2550,
        currency="CNY",
        flow_type=flow,
        merchant=merchant,
        description=description,
        category=Category.pending,
        row_id=row_id,
        classification_source=ClassificationSource.pending,
        classification_reason="待分类",
        duplicate_status="unique",
        issues=[],
    )


class _FakeOcrEngine:
    def __init__(self, lines: list[OcrLine] | Exception) -> None:
        self._lines = lines

    def extract(self, data: bytes) -> list[OcrLine]:
        if isinstance(self._lines, Exception):
            raise self._lines
        return list(self._lines)


def _line(text: str, y: float, x: float = 20.0) -> OcrLine:
    return OcrLine(text=text, x_min=x, y_center=y, height=20.0, confidence=0.98)


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (120, 80), "white").save(buf, format="PNG")
    return buf.getvalue()


def _find_cjk_font() -> str | None:
    candidates = (
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    )
    for path in candidates:
        if Path(path).is_file():
            return path
    return None


class ProviderLoadingTest(unittest.TestCase):
    def test_factory_loads_deepseek_intelligence(self) -> None:
        provider = build_intelligence("app.intelligence.deepseek:DeepSeekIntelligence")
        self.assertEqual(provider.name, "deepseek")
        self.assertIsInstance(provider, IntelligenceProvider)


class OcrParsingTest(unittest.TestCase):
    def test_detail_screenshot_extracts_all_fields(self) -> None:
        ocr = _FakeOcrEngine(
            [
                _line("账单详情", 20),
                _line("星巴克咖啡", 60),
                _line("-38.50", 100),
                _line("当前状态", 140, 20),
                _line("支付成功", 140, 140),
                _line("商品", 180, 20),
                _line("拿铁大杯", 180, 140),
                _line("支付时间", 220, 20),
                _line("2026-11-08 09:15:30", 220, 140),
                _line("交易单号", 260, 20),
                _line("4200001234567890123456789012", 260, 140),
            ]
        )
        provider = DeepSeekIntelligence(api_key="", ocr_engine=ocr)
        parsed = provider.recognize_bill_image(_png_bytes(), "image/png", "wechat")
        self.assertEqual(len(parsed.rows), 1)
        row = parsed.rows[0]
        self.assertEqual(row.amount_fen, 3850)
        self.assertEqual(row.flow_type, FlowType.expense)
        self.assertEqual(row.merchant, "星巴克咖啡")
        self.assertEqual(row.description, "拿铁大杯")
        self.assertEqual(row.source_transaction_id, "4200001234567890123456789012")
        self.assertEqual(row.occurred_at, datetime(2026, 11, 8, 9, 15, 30, tzinfo=CST))
        self.assertEqual(row.issues, [])

        # 同图再次识别，row_id 必须稳定可复现
        parsed_again = provider.recognize_bill_image(_png_bytes(), "image/png", "wechat")
        self.assertEqual(parsed_again.rows[0].row_id, row.row_id)

    def test_missing_year_never_guessed(self) -> None:
        """docs/02 & 05：截图时间缺年份不得默补当前年，必须置 None 并给 TIME_MISSING。"""
        ocr = _FakeOcrEngine(
            [
                _line("账单详情", 20),
                _line("美团外卖", 60),
                _line("-24.00", 100),
                _line("支付时间 11-08 12:30", 140),
            ]
        )
        provider = DeepSeekIntelligence(api_key="", ocr_engine=ocr)
        parsed = provider.recognize_bill_image(_png_bytes(), "image/png", "alipay")
        self.assertEqual(len(parsed.rows), 1)
        row = parsed.rows[0]
        self.assertIsNone(row.occurred_at)
        self.assertIn(ISSUE_TIME_MISSING, [i.code for i in row.issues])

    def test_multi_row_list_screenshot(self) -> None:
        ocr = _FakeOcrEngine(
            [
                _line("全部账单", 20),
                _line("瑞幸咖啡", 70, 20),
                _line("-19.90", 70, 220),
                _line("2026-11-09 08:40", 95, 20),
                _line("某公司报销转入", 150, 20),
                _line("+120.00", 150, 220),
                _line("11月09日 18:10", 175, 20),
            ]
        )
        provider = DeepSeekIntelligence(api_key="", ocr_engine=ocr)
        parsed = provider.recognize_bill_image(_png_bytes(), "image/png", "wechat")
        self.assertEqual(len(parsed.rows), 2)
        first, second = parsed.rows
        self.assertEqual(first.amount_fen, 1990)
        self.assertEqual(first.flow_type, FlowType.expense)
        self.assertEqual(first.occurred_at, datetime(2026, 11, 9, 8, 40, tzinfo=CST))
        self.assertEqual(second.amount_fen, 12000)
        self.assertEqual(second.flow_type, FlowType.income)
        self.assertIsNone(second.occurred_at)
        self.assertIn(ISSUE_TIME_MISSING, [i.code for i in second.issues])

    def test_missing_flow_and_merchant_mark_issues(self) -> None:
        ocr = _FakeOcrEngine(
            [
                _line("账单详情", 20),
                _line("¥45.00", 80),
                _line("付款时间 2026-11-10 10:00", 120),
            ]
        )
        provider = DeepSeekIntelligence(api_key="", ocr_engine=ocr)
        parsed = provider.recognize_bill_image(_png_bytes(), "image/png", "alipay")
        codes = [i.code for i in parsed.rows[0].issues]
        self.assertIn(ISSUE_FLOW_TYPE_UNKNOWN, codes)
        self.assertIn(ISSUE_MERCHANT_MISSING, codes)

    def test_void_transaction_skipped_with_issue(self) -> None:
        ocr = _FakeOcrEngine(
            [
                _line("账单详情", 20),
                _line("测试商户", 60),
                _line("-88.00", 100),
                _line("当前状态 交易关闭", 140),
            ]
        )
        provider = DeepSeekIntelligence(api_key="", ocr_engine=ocr)
        parsed = provider.recognize_bill_image(_png_bytes(), "image/png", "alipay")
        self.assertEqual(parsed.rows, [])
        self.assertEqual([i.code for i in parsed.issues], [ISSUE_ROWS_SKIPPED])

    def test_corrupted_and_blank_images_fail_safely(self) -> None:
        provider = DeepSeekIntelligence(api_key="")
        with self.assertRaises(IntelligenceFailure) as bad_ctx:
            provider.recognize_bill_image(b"not-an-image", "image/png", "wechat")
        self.assertEqual(bad_ctx.exception.code, INVALID_FILE)

        blank_provider = DeepSeekIntelligence(api_key="", ocr_engine=_FakeOcrEngine([]))
        with self.assertRaises(IntelligenceFailure) as blank_ctx:
            blank_provider.recognize_bill_image(_png_bytes(), "image/png", "wechat")
        self.assertEqual(blank_ctx.exception.code, OCR_FIELD_MISSING)

        down_provider = DeepSeekIntelligence(
            api_key="",
            ocr_engine=_FakeOcrEngine(IntelligenceFailure(OCR_UNAVAILABLE, "engine down")),
        )
        with self.assertRaises(IntelligenceFailure) as down_ctx:
            down_provider.recognize_bill_image(_png_bytes(), "image/png", "wechat")
        self.assertEqual(down_ctx.exception.code, OCR_UNAVAILABLE)

    def test_real_rapidocr_synthetic_screenshot(self) -> None:
        """真实调用本地 RapidOCR 对合成账单截图做像素级识别。"""
        font_path = _find_cjk_font()
        if font_path is None:
            self.skipTest("当前环境无可用中文字体，跳过像素级中文渲染测试")

        img = Image.new("RGB", (760, 480), "white")
        draw = ImageDraw.Draw(img)
        font_title = ImageFont.truetype(font_path, 28)
        font_body = ImageFont.truetype(font_path, 24)
        lines = [
            "账单详情",
            "星巴克咖啡",
            "-35.00",
            "当前状态 支付成功",
            "商品 拿铁咖啡",
            "支付时间 2026-11-10 09:15:00",
            "交易单号 4200009988776655",
        ]
        y = 30
        for idx, text in enumerate(lines):
            draw.text((40, y), text, fill="black", font=font_title if idx < 3 else font_body)
            y += 58
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        provider = DeepSeekIntelligence(api_key="")
        parsed = provider.recognize_bill_image(buf.getvalue(), "image/png", "wechat")
        self.assertEqual(len(parsed.rows), 1)
        row = parsed.rows[0]
        self.assertEqual(row.amount_fen, 3500)
        self.assertEqual(row.flow_type, FlowType.expense)
        self.assertEqual(row.occurred_at, datetime(2026, 11, 10, 9, 15, 0, tzinfo=CST))


class DeepSeekClassificationTest(unittest.TestCase):
    def test_priority_and_sanitized_payload(self) -> None:
        captured_payloads: list[dict] = []

        def transport(url, headers, payload, timeout):
            captured_payloads.append(payload)
            return 200, {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "items": [
                                        {
                                            "row_id": "r3",
                                            "category": "health",
                                            "reason": "社区健康服务中心属于医疗健康",
                                        }
                                    ]
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
            }

        rule = ClassificationRule(
            id="rule-1",
            version=1,
            source=Source.wechat,
            merchant_normalized=normalize_merchant("星巴克咖啡"),
            category=Category.shopping,
            enabled=True,
        )
        rows = [
            _draft("r1", "星巴克咖啡"),
            _draft("r2", "北京地铁"),
            _draft("r3", "社区健康服务中心", "年度常规复查", order_id="SENSITIVE-ORDER-999"),
        ]
        provider = DeepSeekIntelligence(api_key="sk-test-123", transport=transport)
        results = provider.classify_transactions(rows, [rule], use_llm=True)

        self.assertEqual(results[0].category, Category.shopping)
        self.assertEqual(results[0].classification_source, ClassificationSource.user_rule)
        self.assertEqual(results[1].category, Category.transport)
        self.assertEqual(results[1].classification_source, ClassificationSource.general_rule)
        self.assertEqual(results[2].category, Category.health)
        self.assertEqual(results[2].classification_source, ClassificationSource.deepseek)

        # 只有未命中规则的 r3 发给 DeepSeek，且不得携带交易单号
        self.assertEqual(len(captured_payloads), 1)
        sent_user_msg = captured_payloads[0]["messages"][1]["content"]
        self.assertNotIn("r1", sent_user_msg)
        self.assertNotIn("r2", sent_user_msg)
        self.assertNotIn("SENSITIVE-ORDER-999", sent_user_msg)
        self.assertEqual(provider.last_usage_stats["total_tokens"], 70)

    def test_retries_once_on_timeout_then_succeeds(self) -> None:
        attempts = 0

        def flaky_transport(url, headers, payload, timeout):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise TimeoutError("simulated timeout")
            return 200, {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"items": [{"row_id": "r1", "category": "other", "reason": "杂项"}]}
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }

        provider = DeepSeekIntelligence(api_key="sk-test-123", transport=flaky_transport)
        results = provider.classify_transactions([_draft("r1", "未知商铺")], [], use_llm=True)
        self.assertEqual(attempts, 2)
        self.assertEqual(results[0].category, Category.other)
        self.assertEqual(results[0].classification_source, ClassificationSource.deepseek)

    def test_timeout_falls_back_to_pending_without_faking_source(self) -> None:
        def always_timeout(url, headers, payload, timeout):
            raise TimeoutError("timed out")

        provider = DeepSeekIntelligence(api_key="sk-test-123", transport=always_timeout)
        rows = [_draft("r1", "麦当劳"), _draft("r2", "未知商铺A")]
        results = provider.classify_transactions(rows, [], use_llm=True)
        self.assertEqual(results[0].classification_source, ClassificationSource.general_rule)
        self.assertEqual(results[1].category, Category.pending)
        self.assertEqual(results[1].classification_source, ClassificationSource.pending)
        self.assertEqual([i.code for i in results[1].issues], [MODEL_TIMEOUT])

    def test_duplicate_unknown_missing_row_ids_never_mismatch(self) -> None:
        def bad_mapping_transport(url, headers, payload, timeout):
            return 200, {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "items": [
                                        {"row_id": "r1", "category": "dining", "reason": "dup1"},
                                        {"row_id": "r1", "category": "shopping", "reason": "dup2"},
                                        {"row_id": "unknown-99", "category": "health", "reason": "x"},
                                        {"row_id": "r3", "category": "not_a_category", "reason": "bad"},
                                    ]
                                }
                            )
                        }
                    }
                ]
            }

        provider = DeepSeekIntelligence(api_key="sk-test-123", transport=bad_mapping_transport)
        rows = [_draft("r1", "未知甲"), _draft("r2", "未知乙"), _draft("r3", "未知丙")]
        results = provider.classify_transactions(rows, [], use_llm=True)
        self.assertEqual([r.row_id for r in results], ["r1", "r2", "r3"])
        self.assertTrue(all(r.category == Category.pending for r in results))
        self.assertTrue(all(r.classification_source == ClassificationSource.pending for r in results))
        self.assertEqual(results[0].issues[0].code, MODEL_OUTPUT_INVALID)
        self.assertEqual(results[1].issues[0].code, MODEL_OUTPUT_INVALID)
        self.assertEqual(results[2].issues[0].code, ISSUE_CATEGORY_UNCERTAIN)

    def test_batch_concurrency_respects_all_rows(self) -> None:
        def batch_transport(url, headers, payload, timeout):
            txs = json.loads(payload["messages"][1]["content"])["transactions"]
            return 200, {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "items": [
                                        {"row_id": tx["row_id"], "category": "other", "reason": "ok"}
                                        for tx in txs
                                    ]
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
            }

        provider = DeepSeekIntelligence(
            api_key="sk-test-123", batch_size=2, transport=batch_transport
        )
        rows = [_draft(f"r{i}", f"未知商户{i}") for i in range(5)]
        results = provider.classify_transactions(rows, [], use_llm=True)
        self.assertEqual(len(results), 5)
        self.assertTrue(all(r.classification_source == ClassificationSource.deepseek for r in results))
        self.assertEqual(provider.last_usage_stats["batches"], 3)
        self.assertEqual(provider.last_usage_stats["total_tokens"], 90)


class ScreenshotImportApiFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Base.metadata.create_all(app.state.engine)
        factory = app.state.session_factory
        with factory() as db:
            if not db.scalar(select(models.User).where(models.User.username == "ocr_tester")):
                db.add(
                    models.User(
                        id=str(uuid.uuid4()),
                        username="ocr_tester",
                        password_hash=hash_password("OcrPass@2026"),
                        is_active=True,
                    )
                )
                db.commit()

    def test_screenshot_upload_process_and_confirm(self) -> None:
        with TestClient(app) as client:
            login = client.post(
                "/api/auth/login",
                json={"username": "ocr_tester", "password": "OcrPass@2026"},
            )
            self.assertEqual(login.status_code, 200)
            csrf = login.json()["csrf_token"]

            resp = client.post(
                "/api/imports",
                headers={"X-CSRF-Token": csrf},
                data={"source": "wechat", "ingestion_method": "screenshot"},
                files={"file": ("shot.png", _png_bytes(), "image/png")},
            )
            self.assertEqual(resp.status_code, 202)
            batch_id = resp.json()["id"]

            # 注入测试替身 OCR 跑一次批次处理
            fake_ocr = _FakeOcrEngine(
                [
                    _line("账单详情", 20),
                    _line("瑞幸咖啡", 60),
                    _line("-18.00", 100),
                    _line("支付时间 2026-11-11 14:20:00", 140),
                    _line("交易单号 wx_ocr_20261111_01", 180),
                ]
            )
            provider = DeepSeekIntelligence(api_key="", ocr_engine=fake_ocr)
            with app.state.session_factory() as db:
                batch = db.get(models.ImportBatch, batch_id)
                assert batch is not None
                import_service.process_batch(db, batch, provider, app.state.settings)

            detail = client.get(f"/api/imports/{batch_id}")
            self.assertEqual(detail.status_code, 200)
            body = detail.json()
            self.assertEqual(body["status"], BatchStatus.pending_review.value)
            self.assertEqual(len(body["rows"]), 1)
            row = body["rows"][0]
            self.assertEqual(row["amount_fen"], 1800)
            self.assertEqual(row["category"], "dining")
            self.assertEqual(row["classification_source"], "general_rule")

            orig = client.get(f"/api/imports/{batch_id}/original")
            self.assertEqual(orig.status_code, 200)
            self.assertEqual(orig.headers["content-type"], "image/png")

            confirm = client.post(
                f"/api/imports/{batch_id}/confirm",
                headers={"X-CSRF-Token": csrf},
                json={
                    "request_id": "req-ocr-confirm-1",
                    "expected_version": body["version"],
                    "rows": [
                        {
                            "row_id": row["row_id"],
                            "allow_suspected_duplicate": False,
                            "transaction": {
                                "source_transaction_id": row["source_transaction_id"],
                                "occurred_at": row["occurred_at"],
                                "amount_fen": row["amount_fen"],
                                "currency": "CNY",
                                "flow_type": row["flow_type"],
                                "merchant": row["merchant"],
                                "description": row["description"],
                                "category": row["category"],
                            },
                        }
                    ],
                },
            )
            self.assertEqual(confirm.status_code, 200)
            self.assertEqual(confirm.json()["created_count"], 1)


class ResolveMissingFieldsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Base.metadata.create_all(app.state.engine)
        factory = app.state.session_factory
        with factory() as db:
            for uname in ("resolve_user", "resolve_other"):
                if not db.scalar(select(models.User).where(models.User.username == uname)):
                    db.add(
                        models.User(
                            id=str(uuid.uuid4()),
                            username=uname,
                            password_hash=hash_password("ResolvePass@2026"),
                            is_active=True,
                        )
                    )
            db.commit()

    def test_deterministic_and_deepseek_resolve_missing(self) -> None:
        drafts = [
            TransactionDraft(
                source_transaction_id=None,
                occurred_at=None,
                amount_fen=98057,
                currency="CNY",
                flow_type=FlowType.expense,
                merchant="医院 13800138000",
                description="",
                category=Category.health,
                row_id="row_m1",
                classification_source=ClassificationSource.deepseek,
                classification_reason="医疗消费",
                duplicate_status="unique",
                issues=[
                    Issue(
                        row_id="row_m1",
                        field="occurred_at",
                        code=ISSUE_TIME_MISSING,
                        message="截图时间缺少具体年份（11月6日16:53），请手动补全完整日期",
                    )
                ],
            ),
            TransactionDraft(
                source_transaction_id=None,
                occurred_at=None,
                amount_fen=22000,
                currency="CNY",
                flow_type=FlowType.transfer,
                merchant="刘家铭",
                description="",
                category=Category.pending,
                row_id="row_m2",
                classification_source=ClassificationSource.pending,
                classification_reason="待用户确认",
                duplicate_status="unique",
                issues=[
                    Issue(
                        row_id="row_m2",
                        field="occurred_at",
                        code=ISSUE_TIME_MISSING,
                        message="截图时间缺少具体年份（11月6日17:08），请手动补全完整日期",
                    ),
                    Issue(
                        row_id="row_m2",
                        field="category",
                        code=ISSUE_CATEGORY_UNCERTAIN,
                        message="无法自动判断类别，请手动选择",
                    ),
                ],
            ),
            TransactionDraft(
                source_transaction_id=None,
                occurred_at=None,
                amount_fen=2560,
                currency="CNY",
                flow_type=FlowType.expense,
                merchant="水电服务",
                description="",
                category=Category.housing,
                row_id="row_m3",
                classification_source=ClassificationSource.general_rule,
                classification_reason="命中居住规则",
                duplicate_status="unique",
                issues=[
                    Issue(
                        row_id="row_m3",
                        field="occurred_at",
                        code=ISSUE_TIME_MISSING,
                        message="截图中未识别到交易时间，请手动补全",
                    )
                ],
            ),
        ]

        # 纯年份快捷补全：前两笔有局部日期的补齐，第3笔无月日信息不编造
        year_only = resolve_missing_deterministic(drafts, default_year=2026)
        self.assertEqual(year_only[0].occurred_at, datetime(2026, 11, 6, 16, 53, tzinfo=CST))
        self.assertEqual(year_only[1].occurred_at, datetime(2026, 11, 6, 17, 8, tzinfo=CST))
        self.assertIsNone(year_only[2].occurred_at)
        self.assertEqual(year_only[0].issues, [])
        self.assertEqual([i.code for i in year_only[1].issues], [ISSUE_CATEGORY_UNCERTAIN])

        # DeepSeek 自然语言对话补全 + 长数字脱敏校验
        captured: dict = {}

        def fake_transport(url, headers, payload, timeout):
            captured["user"] = json.loads(payload["messages"][1]["content"])
            return 200, {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "updates": [
                                        {
                                            "row_id": "row_m1",
                                            "occurred_at": "2026-11-06T16:53:00+08:00",
                                        },
                                        {
                                            "row_id": "row_m2",
                                            "occurred_at": "2026-11-06T17:08:00+08:00",
                                            "category": "other",
                                            "reason": "用户说明亲友转账归其他",
                                        },
                                        {
                                            "row_id": "row_m3",
                                            "occurred_at": "2026-11-01T12:00:00+08:00",
                                        },
                                    ]
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {"total_tokens": 50},
            }

        provider = DeepSeekIntelligence(api_key="sk-test-resolve", transport=fake_transport)
        resolved = provider.resolve_missing_fields(
            drafts,
            default_year=2026,
            instruction="前2笔是2026年，第3笔是2026年11月1日 12:00，第2笔归类为其他",
        )
        self.assertNotIn("13800138000", json.dumps(captured["user"], ensure_ascii=False))
        self.assertEqual(resolved[2].occurred_at, datetime(2026, 11, 1, 12, 0, tzinfo=CST))
        self.assertEqual(resolved[1].category, Category.other)
        self.assertEqual(resolved[1].classification_source, ClassificationSource.deepseek)
        self.assertTrue(all(not r.issues for r in resolved))

    def test_resolve_missing_api_flow_and_duplicate_recheck(self) -> None:
        prev_provider = getattr(app.state, "intelligence_provider", None)
        try:
            with TestClient(app) as client:
                login = client.post(
                    "/api/auth/login",
                    json={"username": "resolve_user", "password": "ResolvePass@2026"},
                )
                self.assertEqual(login.status_code, 200)
                csrf = login.json()["csrf_token"]

                # 先入账一笔 2026-11-06 16:53 医疗 ¥980.57（后续补充年份后应命中判重）
                fake_shot = _FakeOcrEngine(
                    [
                        _line("微信支付账单", 10),
                        _line("医疗", 50, 20),
                        _line("-980.57", 50, 120),
                        _line("北京中医药大学深圳医院", 70, 20),
                        _line("11月6日 16:53", 70, 120),
                        _line("转账", 120, 20),
                        _line("-220.00", 120, 120),
                        _line("刘家铭", 140, 20),
                        _line("11月6日 17:08", 140, 120),
                        _line("餐饮", 190, 20),
                        _line("-31.90", 190, 120),
                        _line("塔斯汀中国汉堡", 210, 20),
                    ]
                )

                up1 = client.post(
                    "/api/imports",
                    headers={"X-CSRF-Token": csrf},
                    data={"source": "wechat", "ingestion_method": "screenshot"},
                    files={"file": ("shot1.png", _png_bytes(), "image/png")},
                )
                self.assertEqual(up1.status_code, 202)
                batch1_id = up1.json()["id"]

                offline_provider = DeepSeekIntelligence(api_key="", ocr_engine=fake_shot)
                with app.state.session_factory() as db:
                    b1 = db.get(models.ImportBatch, batch1_id)
                    assert b1 is not None
                    import_service.process_batch(db, b1, offline_provider, app.state.settings)

                # 先用快捷年份补全前2笔（第3笔无时间留空）
                r_detail = client.get(f"/api/imports/{batch1_id}").json()
                self.assertTrue(any(i["code"] == ISSUE_TIME_MISSING for i in r_detail["issues"]))

                # 缺 CSRF 403 / 空参数 422 / 版本冲突 409
                no_csrf = client.post(
                    f"/api/imports/{batch1_id}/resolve-missing",
                    json={"expected_version": r_detail["version"], "default_year": 2026},
                )
                self.assertEqual(no_csrf.status_code, 403)

                bad_empty = client.post(
                    f"/api/imports/{batch1_id}/resolve-missing",
                    headers={"X-CSRF-Token": csrf},
                    json={"expected_version": r_detail["version"], "default_year": None, "instruction": "   "},
                )
                self.assertEqual(bad_empty.status_code, 422)

                stale = client.post(
                    f"/api/imports/{batch1_id}/resolve-missing",
                    headers={"X-CSRF-Token": csrf},
                    json={"expected_version": 999, "default_year": 2026},
                )
                self.assertEqual(stale.status_code, 409)
                self.assertEqual(stale.json()["error"]["code"], "VERSION_CONFLICT")

                # 注入超时的 DeepSeek 验证 503 SERVICE_UNAVAILABLE
                def timeout_transport(*_args, **_kwargs):
                    raise TimeoutError("timed out")

                app.state.intelligence_provider = DeepSeekIntelligence(
                    api_key="sk-timeout", transport=timeout_transport
                )
                down = client.post(
                    f"/api/imports/{batch1_id}/resolve-missing",
                    headers={"X-CSRF-Token": csrf},
                    json={
                        "expected_version": r_detail["version"],
                        "instruction": "第1笔2026年，第3笔2026年11月1日 12:00",
                    },
                )
                self.assertEqual(down.status_code, 503)

                # 使用正常 mocked DeepSeek 完成全部 3 笔
                def ok_transport(url, headers, payload, timeout):
                    req = json.loads(payload["messages"][1]["content"])
                    row_ids = [r["row_id"] for r in req["rows"]]
                    return 200, {
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(
                                        {
                                            "updates": [
                                                {
                                                    "row_id": row_ids[0],
                                                    "occurred_at": "2026-11-06T16:53:00+08:00",
                                                },
                                                {
                                                    "row_id": row_ids[1],
                                                    "occurred_at": "2026-11-06T17:08:00+08:00",
                                                    "category": "other",
                                                    "reason": "转账归其他",
                                                },
                                                {
                                                    "row_id": row_ids[2],
                                                    "occurred_at": "2026-11-01T12:00:00+08:00",
                                                },
                                            ]
                                        }
                                    )
                                }
                            }
                        ]
                    }

                app.state.intelligence_provider = DeepSeekIntelligence(
                    api_key="sk-ok", transport=ok_transport
                )
                resolved_resp = client.post(
                    f"/api/imports/{batch1_id}/resolve-missing",
                    headers={"X-CSRF-Token": csrf},
                    json={
                        "expected_version": r_detail["version"],
                        "default_year": 2026,
                        "instruction": "前2笔是2026年，第3笔是2026年11月1日 12:00，第2笔归为其他",
                    },
                )
                self.assertEqual(resolved_resp.status_code, 200)
                b1_after = resolved_resp.json()
                self.assertEqual(b1_after["version"], r_detail["version"] + 1)
                self.assertTrue(all(r["occurred_at"] for r in b1_after["rows"]))
                self.assertEqual(b1_after["rows"][1]["category"], "other")

                # 确认第一笔入账
                first = b1_after["rows"][0]
                confirm = client.post(
                    f"/api/imports/{batch1_id}/confirm",
                    headers={"X-CSRF-Token": csrf},
                    json={
                        "request_id": "req-resolve-confirm-1",
                        "expected_version": b1_after["version"],
                        "rows": [
                            {
                                "row_id": first["row_id"],
                                "allow_suspected_duplicate": False,
                                "transaction": {
                                    "source_transaction_id": first["source_transaction_id"],
                                    "occurred_at": first["occurred_at"],
                                    "amount_fen": first["amount_fen"],
                                    "currency": "CNY",
                                    "flow_type": first["flow_type"],
                                    "merchant": first["merchant"],
                                    "description": first["description"],
                                    "category": first["category"],
                                },
                            }
                        ],
                    },
                )
                self.assertEqual(confirm.status_code, 200)
                self.assertEqual(confirm.json()["created_count"], 1)

                # 对已完成批次再调 resolve-missing 应返回 409 BATCH_STATE_CONFLICT
                done_conflict = client.post(
                    f"/api/imports/{batch1_id}/resolve-missing",
                    headers={"X-CSRF-Token": csrf},
                    json={"expected_version": b1_after["version"] + 1, "default_year": 2026},
                )
                self.assertEqual(done_conflict.status_code, 409)

                # 再传同一份无年份截图：刚上传识别时第1笔因缺年份为 unique，
                # 补全年份 2026 后重跑判重应自动检出第1笔为 duplicate！
                up2 = client.post(
                    "/api/imports",
                    headers={"X-CSRF-Token": csrf},
                    data={"source": "wechat", "ingestion_method": "screenshot"},
                    files={"file": ("shot2.png", _png_bytes(), "image/png")},
                )
                self.assertEqual(up2.status_code, 202)
                batch2_id = up2.json()["id"]
                with app.state.session_factory() as db:
                    b2 = db.get(models.ImportBatch, batch2_id)
                    assert b2 is not None
                    import_service.process_batch(db, b2, offline_provider, app.state.settings)

                b2_before = client.get(f"/api/imports/{batch2_id}").json()
                self.assertEqual(b2_before["rows"][0]["duplicate_status"], "unique")

                b2_after_resp = client.post(
                    f"/api/imports/{batch2_id}/resolve-missing",
                    headers={"X-CSRF-Token": csrf},
                    json={"expected_version": b2_before["version"], "default_year": 2026},
                )
                self.assertEqual(b2_after_resp.status_code, 200)
                b2_after = b2_after_resp.json()
                self.assertEqual(b2_after["rows"][0]["duplicate_status"], "duplicate")
                self.assertTrue(
                    any(i["code"] == "DUPLICATE_EXISTING" for i in b2_after["rows"][0]["issues"])
                )
                self.assertEqual(b2_after["rows"][1]["duplicate_status"], "unique")

                # 越权访问其他用户批次应返回 404
                with TestClient(app) as other_client:
                    other_login = other_client.post(
                        "/api/auth/login",
                        json={"username": "resolve_other", "password": "ResolvePass@2026"},
                    )
                    other_csrf = other_login.json()["csrf_token"]
                    not_owned = other_client.post(
                        f"/api/imports/{batch2_id}/resolve-missing",
                        headers={"X-CSRF-Token": other_csrf},
                        json={"expected_version": b2_after["version"], "default_year": 2026},
                    )
                    self.assertEqual(not_owned.status_code, 404)
        finally:
            app.state.intelligence_provider = prev_provider


if __name__ == "__main__":
    unittest.main()

