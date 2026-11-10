"""月度报表口径测试。

用例直接对应 docs/08 的验收项：
- A09：fixtures 口径 I=10000、E=4200、R=500、净支出 3700、差额 6300（单位分）
- A10：餐饮预算 2000 对净支出 2500 超 500；购物预算 1500 对 1200 剩 300；0 预算不除零

这些数字是评委可以自己算的，所以测试里写死，不允许"看起来差不多"。

运行（在 backend/ 目录）：
    python -m unittest tests.test_reporting -v
"""

from __future__ import annotations

import tempfile
import unittest
import uuid
from datetime import date
from pathlib import Path

from app import models
from app.crypto import encrypt_json
from app.db import Base, build_engine, build_session_factory
from app.services.reporting import build_monthly_report, compute_totals, month_days

KEY = "test-data-key-not-for-production"
USER = "user-under-test"
OTHER = "another-user"


def _tx(
    db,
    user_id: str,
    seq: int,
    amount_fen: int,
    flow_type: str,
    category: str,
    occurred_at: str,
    status: str = "confirmed",
) -> None:
    payload = {
        "id": f"tx-{user_id}-{seq}",
        "version": 1,
        "source": "alipay",
        "ingestion_method": "file",
        "import_batch_id": None,
        "source_transaction_id": f"SRC{seq}",
        "occurred_at": occurred_at,
        "amount_fen": amount_fen,
        "currency": "CNY",
        "flow_type": flow_type,
        "merchant": "测试商户",
        "description": "",
        "category": category,
        "classification_source": "manual",
        "classification_reason": "测试固定值",
        "status": status,
    }
    db.add(
        models.Transaction(
            id=f"tx-{user_id}-{seq}",
            user_id=user_id,
            import_batch_id=None,
            version=1,
            month_index=occurred_at[:7],
            source="alipay",
            flow_type=flow_type,
            category=category,
            status=status,
            dedupe_digest=f"digest-{user_id}-{seq}",
            encrypted_payload=encrypt_json(KEY, payload),
        )
    )


def _budget(db, month: str, category: str, amount_fen: int) -> None:
    db.add(
        models.Budget(
            id=str(uuid.uuid4()),
            user_id=USER,
            month=month,
            category=category,
            encrypted_payload=encrypt_json(
                KEY, {"amount_fen": amount_fen, "month": month, "category": category}
            ),
        )
    )


class ReportingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.mkdtemp(prefix="mbl_report_test_")
        cls.engine = build_engine(f"sqlite+pysqlite:///{Path(cls._tmp, 'r.db').as_posix()}")
        Base.metadata.create_all(cls.engine)
        cls.factory = build_session_factory(cls.engine)

        with cls.factory() as db:
            db.add(models.User(id=USER, username="report_a", password_hash="x", is_active=True))
            db.add(models.User(id=OTHER, username="report_b", password_hash="x", is_active=True))
            # 没有 relationship 声明，SQLAlchemy 不知道 users 必须先于 transactions/budgets
            # 落库；显式 flush 一次，避免 FOREIGN KEY constraint failed
            db.flush()

            # A09 场景：2026-11
            _tx(db, USER, 1, 1000000, "income", "salary", "2026-11-10T09:00:00+08:00")
            _tx(db, USER, 2, 250000, "expense", "dining", "2026-11-01T12:00:00+08:00")
            _tx(db, USER, 3, 120000, "expense", "shopping", "2026-11-03T20:00:00+08:00")
            _tx(db, USER, 4, 50000, "expense", "transport", "2026-11-05T08:00:00+08:00")
            _tx(db, USER, 5, 50000, "refund", "dining", "2026-11-06T10:00:00+08:00")
            # 未确认的行不能进报表
            _tx(
                db, USER, 6, 999900, "expense", "dining",
                "2026-11-07T10:00:00+08:00", status="pending_review",
            )
            # 另一个用户的交易不得混入
            _tx(db, OTHER, 7, 777700, "expense", "dining", "2026-11-01T12:00:00+08:00")

            # A10 场景：2026-10（退款落在 other，使餐饮/购物净支出分别为 2500 / 1200）
            _tx(db, USER, 11, 250000, "expense", "dining", "2026-10-02T12:00:00+08:00")
            _tx(db, USER, 12, 120000, "expense", "shopping", "2026-10-03T12:00:00+08:00")
            _tx(db, USER, 13, 50000, "refund", "other", "2026-10-04T12:00:00+08:00")
            _budget(db, "2026-10", "dining", 200000)
            _budget(db, "2026-10", "shopping", 150000)
            _budget(db, "2026-10", "education", 0)
            db.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def _report(self, month: str):
        with self.factory() as db:
            return build_monthly_report(db, USER, month, KEY)

    # ---- A09 ----

    def test_a09_totals(self) -> None:
        report = self._report("2026-11")
        self.assertEqual(report.totals.income_fen, 1000000)
        self.assertEqual(report.totals.gross_expense_fen, 420000)
        self.assertEqual(report.totals.refund_fen, 50000)
        self.assertEqual(report.totals.net_expense_fen, 370000)
        self.assertEqual(report.totals.balance_fen, 630000)

    def test_unconfirmed_excluded(self) -> None:
        """pending_review 的 9999 元不能进报表，否则确认与否都没意义。"""
        report = self._report("2026-11")
        self.assertEqual(report.totals.gross_expense_fen, 420000)

    def test_other_user_isolated(self) -> None:
        report = self._report("2026-11")
        self.assertNotEqual(report.totals.gross_expense_fen, 420000 + 777700)

    def test_expense_by_category_is_gross(self) -> None:
        """饼图用毛支出构成，退款不回冲——净额是另一回事，混在一起图就错了。"""
        report = self._report("2026-11")
        amounts = {item.category.value: item.amount_fen for item in report.expense_by_category}
        self.assertEqual(amounts["dining"], 250000)
        self.assertEqual(amounts["shopping"], 120000)
        self.assertEqual(amounts["transport"], 50000)

    def test_only_positive_categories(self) -> None:
        report = self._report("2026-11")
        self.assertTrue(all(item.amount_fen > 0 for item in report.expense_by_category))
        # salary 是收入，不该出现在支出构成里
        self.assertNotIn("salary", [item.category.value for item in report.expense_by_category])

    def test_daily_trend_covers_whole_month(self) -> None:
        report = self._report("2026-11")
        self.assertEqual(len(report.daily_trend), 30)
        self.assertEqual(report.daily_trend[0].date, date(2026, 11, 1))
        self.assertEqual(report.daily_trend[-1].date, date(2026, 11, 30))

    def test_daily_trend_zero_filled(self) -> None:
        report = self._report("2026-11")
        quiet = [p for p in report.daily_trend if p.date == date(2026, 11, 2)]
        self.assertEqual(len(quiet), 1)
        self.assertEqual(quiet[0].net_expense_fen, 0)

    def test_daily_trend_sums_match_totals(self) -> None:
        report = self._report("2026-11")
        self.assertEqual(
            sum(p.gross_expense_fen for p in report.daily_trend),
            report.totals.gross_expense_fen,
        )
        self.assertEqual(
            sum(p.refund_fen for p in report.daily_trend), report.totals.refund_fen
        )

    # ---- A10 ----

    def test_a10_budget_over(self) -> None:
        report = self._report("2026-10")
        dining = next(b for b in report.budgets if b.category.value == "dining")
        self.assertEqual(dining.budget_fen, 200000)
        self.assertEqual(dining.spent_fen, 250000)
        self.assertEqual(dining.remaining_fen, -50000)
        self.assertEqual(dining.over_fen, 50000)

    def test_a10_budget_remaining(self) -> None:
        report = self._report("2026-10")
        shopping = next(b for b in report.budgets if b.category.value == "shopping")
        self.assertEqual(shopping.spent_fen, 120000)
        self.assertEqual(shopping.remaining_fen, 30000)
        self.assertEqual(shopping.over_fen, 0)

    def test_a10_zero_budget_does_not_divide(self) -> None:
        report = self._report("2026-10")
        education = next(b for b in report.budgets if b.category.value == "education")
        self.assertEqual(education.budget_fen, 0)
        self.assertEqual(education.spent_fen, 0)
        self.assertEqual(education.remaining_fen, 0)
        self.assertEqual(education.over_fen, 0)

    def test_refund_reduces_budget_spend(self) -> None:
        """预算看净支出：退款回到预算里，才符合"这月还能花多少"。"""
        with self.factory() as db:
            db.add(models.User(id="u3", username="u3", password_hash="x", is_active=True))
            db.flush()
            _tx(db, "u3", 21, 100000, "expense", "dining", "2026-09-02T12:00:00+08:00")
            _tx(db, "u3", 22, 30000, "refund", "dining", "2026-09-03T12:00:00+08:00")
            db.add(
                models.Budget(
                    id=str(uuid.uuid4()),
                    user_id="u3",
                    month="2026-09",
                    category="dining",
                    encrypted_payload=encrypt_json(
                        KEY, {"amount_fen": 50000, "month": "2026-09", "category": "dining"}
                    ),
                )
            )
            db.commit()
            report = build_monthly_report(db, "u3", "2026-09", KEY)
        dining = report.budgets[0]
        self.assertEqual(dining.spent_fen, 70000)
        self.assertEqual(dining.remaining_fen, -20000)
        self.assertEqual(dining.over_fen, 20000)

    # ---- 空月份与边界 ----

    def test_empty_month(self) -> None:
        report = self._report("2026-08")
        self.assertEqual(report.totals.income_fen, 0)
        self.assertEqual(report.totals.net_expense_fen, 0)
        self.assertEqual(len(report.daily_trend), 31)
        self.assertEqual(report.expense_by_category, [])
        self.assertEqual(report.budgets, [])

    def test_month_days_february_leap(self) -> None:
        self.assertEqual(len(month_days("2024-02")), 29)
        self.assertEqual(len(month_days("2026-02")), 28)

    def test_budgets_sorted_by_category_order(self) -> None:
        report = self._report("2026-10")
        order = [b.category.value for b in report.budgets]
        self.assertEqual(order, ["dining", "shopping", "education"])


class ComputeTotalsTest(unittest.TestCase):
    def test_refund_subtracts_not_adds(self) -> None:
        """退款是净支出的减项，不是收入。写成收入会让总收入虚高。"""
        totals = compute_totals(
            [
                {"amount_fen": 100, "flow_type": "income"},
                {"amount_fen": 300, "flow_type": "expense"},
                {"amount_fen": 50, "flow_type": "refund"},
            ]
        )
        self.assertEqual(totals.income_fen, 100)
        self.assertEqual(totals.refund_fen, 50)
        self.assertEqual(totals.net_expense_fen, 250)
        self.assertEqual(totals.balance_fen, -150)

    def test_transfer_ignored(self) -> None:
        """内部转账是钱从自己左口袋到右口袋，不能算收入或支出。"""
        totals = compute_totals(
            [
                {"amount_fen": 500, "flow_type": "transfer"},
                {"amount_fen": 100, "flow_type": "expense"},
            ]
        )
        self.assertEqual(totals.income_fen, 0)
        self.assertEqual(totals.gross_expense_fen, 100)

    def test_refund_exceeding_expense_gives_negative_net(self) -> None:
        """跨月退款会让某月净支出为负，契约允许（net_expense_fen 无 ge 约束）。"""
        totals = compute_totals([{"amount_fen": 500, "flow_type": "refund"}])
        self.assertEqual(totals.net_expense_fen, -500)


if __name__ == "__main__":
    unittest.main()
