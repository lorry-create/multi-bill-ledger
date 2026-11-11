"""智能模块解析与分类的行为测试。

不依赖 FastAPI、不连数据库、不占端口：只测纯函数层。
用的样例是 fixtures/real_format_samples 下两份格式仿真的文件（数据全合成）。

运行（在 backend/ 目录）：
    python -m unittest tests.test_intelligence -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.contracts import (
    Category,
    ClassificationRule,
    ClassificationSource,
    FlowType,
    Source,
    TransactionDraft,
)
from app.intelligence import (
    ISSUE_CATEGORY_UNCERTAIN,
    ISSUE_ROWS_SKIPPED,
    OCR_UNAVAILABLE,
    UNSUPPORTED_TEMPLATE,
    IntelligenceFailure,
    assert_one_result_per_row,
    build_intelligence,
    normalize_merchant,
)
from app.intelligence.fallback import parse_amount_fen, parse_occurred_at
from app.intelligence.rules import classify_by_keywords

SAMPLES = Path(__file__).resolve().parents[2] / "fixtures" / "real_format_samples"
ALIPAY = SAMPLES / "alipay_export_sample.csv"
WECHAT = SAMPLES / "wechat_export_sample.csv"

CST = timezone(timedelta(hours=8))


def _draft(row_id: str, merchant: str, description: str = "", flow=FlowType.expense):
    return TransactionDraft(
        source_transaction_id=None,
        occurred_at=datetime(2026, 11, 1, 12, 0, tzinfo=CST),
        amount_fen=1000,
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


class AmountParsingTest(unittest.TestCase):
    def test_strips_currency_and_thousands(self) -> None:
        self.assertEqual(parse_amount_fen("¥1,234.56"), 123456)
        self.assertEqual(parse_amount_fen("￥32.00"), 3200)
        self.assertEqual(parse_amount_fen(" 100 元 "), 10000)

    def test_no_float_drift(self) -> None:
        # 0.1+0.2 用 float 会得到 30.000000000000004 分；Decimal 必须给 30
        self.assertEqual(parse_amount_fen("0.10") + parse_amount_fen("0.20"), 30)

    def test_half_up_rounding(self) -> None:
        self.assertEqual(parse_amount_fen("0.005"), 1)
        self.assertEqual(parse_amount_fen("0.004"), 0)

    def test_unparsable_returns_none(self) -> None:
        for raw in ("", "  ", "abc", "--", "￥"):
            self.assertIsNone(parse_amount_fen(raw), msg=repr(raw))


class TimeParsingTest(unittest.TestCase):
    def test_formats(self) -> None:
        cases = {
            "2026-11-01 12:30:45": datetime(2026, 11, 1, 12, 30, 45, tzinfo=CST),
            "2026-11-01 12:30": datetime(2026, 11, 1, 12, 30, tzinfo=CST),
            "2026-11-01": datetime(2026, 11, 1, 0, 0, tzinfo=CST),
            "2026/11/01 12:30:45": datetime(2026, 11, 1, 12, 30, 45, tzinfo=CST),
        }
        for raw, expected in cases.items():
            self.assertEqual(parse_occurred_at(raw), expected, msg=raw)

    def test_unknown_returns_none(self) -> None:
        for raw in ("", "11月1日 12:30", "2026-13-01"):
            self.assertIsNone(parse_occurred_at(raw), msg=repr(raw))

    def test_result_carries_timezone(self) -> None:
        # 契约要求带时区；naive datetime 会让月份归属悄悄按 UTC 算
        parsed = parse_occurred_at("2026-11-01 00:30:00")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.utcoffset(), timedelta(hours=8))


class MerchantNormalizeTest(unittest.TestCase):
    def test_nfkc_and_casefold(self) -> None:
        self.assertEqual(normalize_merchant("ＭｃＤｏｎａｌｄ"), "mcdonald")

    def test_collapses_whitespace(self) -> None:
        self.assertEqual(normalize_merchant("  麦当劳   深圳店  "), "麦当劳 深圳店")

    def test_drops_invisible_characters(self) -> None:
        # 从网页复制商户名常夹带零宽空格，肉眼不可见但会让规则失配
        self.assertEqual(normalize_merchant("星巴克\u200b咖啡"), "星巴克 咖啡")

    def test_empty(self) -> None:
        self.assertEqual(normalize_merchant(""), "")


class AlipayParseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.provider = build_intelligence()
        cls.result = cls.provider.parse_bill_file(ALIPAY.read_bytes(), ALIPAY.name, "alipay")

    def test_row_count(self) -> None:
        self.assertEqual(len(self.result.rows), 6)

    def test_skips_closed_and_zero_amount(self) -> None:
        codes = [issue.code for issue in self.result.issues]
        self.assertIn(ISSUE_ROWS_SKIPPED, codes)
        # 关闭的 50.00 不能出现在草稿里
        self.assertNotIn(5000, [row.amount_fen for row in self.result.rows])

    def test_amounts_exact(self) -> None:
        amounts = sorted(row.amount_fen for row in self.result.rows)
        self.assertEqual(amounts, [400, 500, 3200, 12900, 250000, 1000000])

    def test_income_classified_as_salary(self) -> None:
        salary = [row for row in self.result.rows if row.flow_type == FlowType.income]
        self.assertEqual(len(salary), 1)
        self.assertEqual(salary[0].amount_fen, 1000000)

    def test_refund_detected(self) -> None:
        refunds = [row for row in self.result.rows if row.flow_type == FlowType.refund]
        self.assertEqual(len(refunds), 1)
        self.assertEqual(refunds[0].amount_fen, 500)

    def test_all_rows_start_pending(self) -> None:
        # 解析阶段不猜类别，分类是独立一步（docs/13 模块划分）
        for row in self.result.rows:
            self.assertEqual(row.category, Category.pending)
            self.assertEqual(row.classification_source, ClassificationSource.pending)

    def test_row_ids_stable_across_runs(self) -> None:
        again = self.provider.parse_bill_file(ALIPAY.read_bytes(), ALIPAY.name, "alipay")
        self.assertEqual(
            [row.row_id for row in self.result.rows],
            [row.row_id for row in again.rows],
        )

    def test_row_ids_unique(self) -> None:
        ids = [row.row_id for row in self.result.rows]
        self.assertEqual(len(ids), len(set(ids)))


class WechatParseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.provider = build_intelligence()
        cls.result = cls.provider.parse_bill_file(WECHAT.read_bytes(), WECHAT.name, "wechat")

    def test_row_count_and_clean(self) -> None:
        self.assertEqual(len(self.result.rows), 6)
        # 尾部说明行不该被当成"金额缺失的坏交易"
        self.assertEqual(self.result.issues, [])

    def test_bom_does_not_break_header(self) -> None:
        # 文件是 utf-8-sig；解错编码会让「交易时间」变成乱码，表头永远找不到
        self.assertTrue(all(row.occurred_at is not None for row in self.result.rows))

    def test_currency_symbol_stripped(self) -> None:
        amounts = sorted(row.amount_fen for row in self.result.rows)
        self.assertEqual(amounts, [2000, 2850, 3500, 5000, 8600, 19900])

    def test_refunded_order_kept_as_expense(self) -> None:
        """微信「已全额退款」的订单仍按支出计入——钱确实付出去过。

        没有可靠退款事件号时不做推断（docs/13），退款会在账单里另有一条记录。
        """
        meituan = [row for row in self.result.rows if "美团" in row.merchant]
        self.assertEqual(len(meituan), 1)
        self.assertEqual(meituan[0].flow_type, FlowType.expense)


class EncodingTest(unittest.TestCase):
    def test_gbk_file_can_be_parsed(self) -> None:
        """支付宝老版导出是 GBK。解错编码不报错，只会让中文列名变乱码。"""
        provider = build_intelligence()
        text = ALIPAY.read_text(encoding="utf-8")
        gbk_bytes = text.encode("gb18030")
        result = provider.parse_bill_file(gbk_bytes, "alipay_gbk.csv", "alipay")
        self.assertEqual(len(result.rows), 6)

    def test_empty_file_rejected(self) -> None:
        with self.assertRaises(IntelligenceFailure) as ctx:
            build_intelligence().parse_bill_file(b"", "empty.csv", "alipay")
        self.assertEqual(ctx.exception.code, "INVALID_FILE")

    def test_unknown_template_rejected(self) -> None:
        payload = "姓名,电话\n张三,123\n".encode("utf-8")
        with self.assertRaises(IntelligenceFailure) as ctx:
            build_intelligence().parse_bill_file(payload, "contacts.csv", "alipay")
        self.assertEqual(ctx.exception.code, UNSUPPORTED_TEMPLATE)

    def test_xls_rejected_explicitly(self) -> None:
        with self.assertRaises(IntelligenceFailure) as ctx:
            build_intelligence().parse_bill_file(b"PK\x03\x04", "old.xls", "alipay")
        self.assertEqual(ctx.exception.code, UNSUPPORTED_TEMPLATE)

    def test_wrong_source_still_detected(self) -> None:
        """用户把支付宝文件标成微信很常见。按内容识别，但平台以真实内容为准。"""
        result = build_intelligence().parse_bill_file(
            ALIPAY.read_bytes(), ALIPAY.name, "wechat"
        )
        self.assertEqual(len(result.rows), 6)


class ClassificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.provider = build_intelligence()

    def test_user_rule_beats_general_rule(self) -> None:
        """个人规则优先：用户把星巴克改成 shopping，就必须是 shopping。"""
        rule = ClassificationRule(
            id="rule-1",
            version=1,
            source=Source.wechat,
            merchant_normalized=normalize_merchant("星巴克咖啡"),
            category=Category.shopping,
            enabled=True,
        )
        results = self.provider.classify_transactions([_draft("r1", "星巴克咖啡")], [rule])
        self.assertEqual(results[0].category, Category.shopping)
        self.assertEqual(results[0].classification_source, ClassificationSource.user_rule)

    def test_disabled_rule_ignored(self) -> None:
        rule = ClassificationRule(
            id="rule-2",
            version=2,
            source=Source.wechat,
            merchant_normalized=normalize_merchant("星巴克咖啡"),
            category=Category.shopping,
            enabled=False,
        )
        results = self.provider.classify_transactions([_draft("r1", "星巴克咖啡")], [rule])
        self.assertEqual(results[0].category, Category.dining)
        self.assertEqual(results[0].classification_source, ClassificationSource.general_rule)

    def test_unmatched_goes_pending_with_issue(self) -> None:
        results = self.provider.classify_transactions([_draft("r1", "某某未知商号")], [])
        self.assertEqual(results[0].category, Category.pending)
        self.assertEqual(results[0].classification_source, ClassificationSource.pending)
        self.assertIn(
            ISSUE_CATEGORY_UNCERTAIN, [issue.code for issue in results[0].issues]
        )

    def test_never_claims_deepseek(self) -> None:
        """兜底实现不许把来源标成 deepseek（docs/08 A06 禁止伪成功）。"""
        rows = [_draft(f"r{i}", "星巴克咖啡") for i in range(3)]
        results = self.provider.classify_transactions(rows, [], use_llm=True)
        self.assertTrue(
            all(item.classification_source != ClassificationSource.deepseek for item in results)
        )

    def test_one_result_per_row_in_order(self) -> None:
        rows = [_draft(f"r{i}", m) for i, m in enumerate(["麦当劳", "地铁", "淘宝"])]
        results = self.provider.classify_transactions(rows, [])
        self.assertEqual([item.row_id for item in results], [row.row_id for row in rows])


class KeywordRuleTest(unittest.TestCase):
    def test_longest_match_wins(self) -> None:
        """「美团买菜」同时含「美团」和「买菜」，必须按更具体的判。"""
        matched = classify_by_keywords("美团买菜", "", FlowType.expense)
        self.assertIsNotNone(matched)
        self.assertEqual(matched[0], Category.dining)

    def test_hongbao_is_not_salary(self) -> None:
        """红包归 other。若归 salary，月报的"工资收入"会虚高。"""
        matched = classify_by_keywords("好友转入", "红包", FlowType.income)
        self.assertIsNotNone(matched)
        self.assertEqual(matched[0], Category.other)

    def test_salary_keyword_hits(self) -> None:
        matched = classify_by_keywords("某某科技有限公司", "11月工资", FlowType.income)
        self.assertIsNotNone(matched)
        self.assertEqual(matched[0], Category.salary)

    def test_unmatched_returns_none(self) -> None:
        self.assertIsNone(classify_by_keywords("某某未知商号", "", FlowType.expense))


class ResultAlignmentTest(unittest.TestCase):
    def test_count_mismatch_rejected(self) -> None:
        rows = [_draft("r1", "麦当劳"), _draft("r2", "地铁")]
        results = build_intelligence().classify_transactions(rows[:1], [])
        with self.assertRaises(IntelligenceFailure):
            assert_one_result_per_row(rows, results)

    def test_unknown_row_id_rejected(self) -> None:
        rows = [_draft("r1", "麦当劳")]
        results = build_intelligence().classify_transactions([_draft("r9", "麦当劳")], [])
        with self.assertRaises(IntelligenceFailure):
            assert_one_result_per_row(rows, results)


class ProviderFactoryTest(unittest.TestCase):
    def test_default_has_local_ocr(self) -> None:
        self.assertEqual(build_intelligence().name, "local-rapidocr")

    def test_unknown_provider_fails_loudly(self) -> None:
        """不存在的实现必须启动即失败，不能静默降级成规则实现。"""
        with self.assertRaises(Exception):
            build_intelligence("no.such.module:Thing")

    def test_image_without_ocr_fails_explicitly(self) -> None:
        with self.assertRaises(IntelligenceFailure) as ctx:
            build_intelligence().recognize_bill_image(b"\x89PNG", "image/png", "alipay")
        self.assertEqual(ctx.exception.code, OCR_UNAVAILABLE)

    def test_failure_has_safe_message(self) -> None:
        exc = IntelligenceFailure("MODEL_TIMEOUT")
        self.assertNotIn("key", exc.message.lower())
        self.assertEqual(exc.as_detail()["code"], "MODEL_TIMEOUT")


if __name__ == "__main__":
    unittest.main()
