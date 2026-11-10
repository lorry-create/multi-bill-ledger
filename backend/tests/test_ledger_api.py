"""账单列表、纠错、月报、预算的端到端测试。

这几个接口最容易出的是**口径不一致**：列表显示 100 元、月报算出 90 元，
谁也说不清哪个对。所以这里的用例不只是"接口能返回 200"，而是逐条钉住：
- 上海自然日的归日（UTC 15:30 属于上海次日）；
- 日期区间两端都包含边界；
- 退款从毛支出里减、转账与还款不进毛支出；
- 改完一条交易，月报数字立刻跟着变；
- 预算用的 `spent_fen` 是净支出而不是毛支出。

运行（在 backend/ 目录）：
    python -m unittest tests.test_ledger_api -v

与 `test_imports_api` 共用同一个临时库（靠 unittest discover 的字母序）。
单独运行本文件时自己设一份环境变量，不会碰到 `backend/local-data/app.db`。
"""

from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from datetime import datetime
from pathlib import Path

_TMP_DIR = tempfile.mkdtemp(prefix="mbl_ledger_test_")
# setdefault：discover 时 test_imports_api 已经设过，保持同一套配置
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault(
    "DATABASE_URL", f"sqlite+pysqlite:///{Path(_TMP_DIR, 'ledger.db').as_posix()}"
)
os.environ.setdefault("SESSION_SECRET", "test-session-secret-not-for-production")
os.environ.setdefault("DATA_ENCRYPTION_KEY", "test-data-key-not-for-production")
os.environ.setdefault("COOKIE_SECURE", "0")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import models  # noqa: E402
from app.crypto import encrypt_json  # noqa: E402
from app.db import Base  # noqa: E402
from app.main import app  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services.dedupe import month_index  # noqa: E402

PASSWORD = "ledger-pass-2026"

# 契约里 Transaction 的全部字段。少一个前端就少一个能展示的字段，得逐个核。
_TXN_KEYS = {
    "source_transaction_id",
    "occurred_at",
    "amount_fen",
    "currency",
    "flow_type",
    "merchant",
    "description",
    "category",
    "id",
    "version",
    "source",
    "ingestion_method",
    "import_batch_id",
    "classification_source",
    "classification_reason",
    "status",
}


def _key() -> str:
    return app.state.settings.data_encryption_key


def _make_user(username: str) -> None:
    db = app.state.session_factory()
    try:
        if db.scalar(select(models.User).where(models.User.username == username)) is None:
            db.add(
                models.User(
                    id=str(uuid.uuid4()),
                    username=username,
                    password_hash=hash_password(PASSWORD),
                    is_active=True,
                )
            )
            db.commit()
    finally:
        db.close()


class LedgerApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Base.metadata.create_all(app.state.engine)

    def setUp(self) -> None:
        self.username = f"ledger_{uuid.uuid4().hex[:12]}"
        _make_user(self.username)
        self.client = TestClient(app)
        self.client.__enter__()
        self.csrf = self._login(self.username)

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)

    # ---------------------------------------------------------------- 工具

    def _login(self, username: str) -> str:
        response = self.client.post(
            "/api/auth/login", json={"username": username, "password": PASSWORD}
        )
        self.assertEqual(200, response.status_code, response.text)
        return response.json()["csrf_token"]

    def _user_id(self, username: str | None = None) -> str:
        target = username if username is not None else self.username
        db = app.state.session_factory()
        try:
            user = db.scalar(select(models.User).where(models.User.username == target))
            assert user is not None, f"用户 {target} 不存在"
            return user.id
        finally:
            db.close()

    def _insert_txn(
        self,
        *,
        occurred_at: str,
        amount_fen: int,
        flow_type: str = "expense",
        category: str = "dining",
        merchant: str = "测试商户",
        source: str = "wechat",
        username: str | None = None,
        classification_source: str = "general_rule",
        classification_reason: str = "命中通用餐饮规则",
        description: str = "",
        source_transaction_id: str | None = None,
        ingestion_method: str = "file",
    ) -> str:
        """直接写库造一笔已确认交易，省掉"上传→确认"的往返。

        import_batch_id 故意留空：绝大多数历史数据没有批次可回查，列表接口
        必须能处理这种情况（契约里该字段不可空，只能给空串）。
        """
        payload = {
            "source_transaction_id": source_transaction_id,
            "occurred_at": occurred_at,
            "amount_fen": amount_fen,
            "currency": "CNY",
            "flow_type": flow_type,
            "merchant": merchant,
            "description": description,
            "category": category,
            "ingestion_method": ingestion_method,
            "classification_source": classification_source,
            "classification_reason": classification_reason,
        }
        record = models.Transaction(
            id=str(uuid.uuid4()),
            user_id=self._user_id(username),
            import_batch_id=None,
            version=1,
            month_index=month_index(datetime.fromisoformat(occurred_at)),
            source=source,
            flow_type=flow_type,
            category=category,
            status="confirmed",
            dedupe_digest=uuid.uuid4().hex,
            encrypted_payload=encrypt_json(_key(), payload),
        )
        db = app.state.session_factory()
        try:
            db.add(record)
            db.commit()
            return record.id
        finally:
            db.close()

    def _list(self, **params) -> dict:
        response = self.client.get("/api/transactions", params=params)
        self.assertEqual(200, response.status_code, response.text)
        return response.json()

    def _patch(self, txn_id: str, body: dict, csrf: str | None = None):
        return self.client.patch(
            f"/api/transactions/{txn_id}",
            json=body,
            headers={"X-CSRF-Token": self.csrf if csrf is None else csrf},
        )

    def _report(self, month: str) -> dict:
        response = self.client.get("/api/reports/monthly", params={"month": month})
        self.assertEqual(200, response.status_code, response.text)
        return response.json()

    def _put_budget(self, month: str, category: str, amount_fen: int):
        return self.client.put(
            "/api/budgets",
            json={"month": month, "category": category, "amount_fen": amount_fen},
            headers={"X-CSRF-Token": self.csrf},
        )

    # ------------------------------------------------------------ 列表接口

    def test_list_requires_login(self) -> None:
        anonymous = TestClient(app)
        response = anonymous.get("/api/transactions")
        self.assertEqual(401, response.status_code)
        # 码必须与契约一致，否则前端写的 code === 'AUTH_REQUIRED' 永远不命中
        self.assertEqual("AUTH_REQUIRED", response.json()["error"]["code"])

    def test_list_returns_contract_fields(self) -> None:
        self._insert_txn(occurred_at="2026-11-08T12:00:00+08:00", amount_fen=2300)
        page = self._list()
        self.assertEqual(1, page["total"])
        self.assertEqual(1, page["page"])
        self.assertEqual(50, page["page_size"])
        item = page["items"][0]
        self.assertEqual(_TXN_KEYS, set(item))
        self.assertEqual("confirmed", item["status"])
        self.assertEqual("CNY", item["currency"])
        # 没有批次时契约要求是字符串，给空串而不是 null
        self.assertEqual("", item["import_batch_id"])
        self.assertEqual("general_rule", item["classification_source"])
        self.assertEqual("命中通用餐饮规则", item["classification_reason"])

    def test_list_only_returns_own_records(self) -> None:
        other = f"ledger_other_{uuid.uuid4().hex[:8]}"
        _make_user(other)
        self._insert_txn(occurred_at="2026-11-08T12:00:00+08:00", amount_fen=1111)
        self._insert_txn(
            occurred_at="2026-11-08T12:00:00+08:00", amount_fen=9999, username=other
        )
        page = self._list()
        self.assertEqual(1, page["total"])
        self.assertEqual(1111, page["items"][0]["amount_fen"])

    def test_list_orders_by_time_then_id_desc(self) -> None:
        early = self._insert_txn(occurred_at="2026-11-01T09:00:00+08:00", amount_fen=100)
        late = self._insert_txn(occurred_at="2026-11-20T09:00:00+08:00", amount_fen=200)
        page = self._list()
        self.assertEqual([late, early], [item["id"] for item in page["items"]])

    def test_date_range_includes_both_ends(self) -> None:
        start = self._insert_txn(occurred_at="2026-11-08T00:00:00+08:00", amount_fen=100)
        end = self._insert_txn(occurred_at="2026-11-08T23:59:59+08:00", amount_fen=200)
        self._insert_txn(occurred_at="2026-11-07T23:59:59+08:00", amount_fen=300)
        self._insert_txn(occurred_at="2026-11-09T00:00:00+08:00", amount_fen=400)

        page = self._list(date_from="2026-11-08", date_to="2026-11-08")
        self.assertEqual(2, page["total"])
        self.assertEqual({start, end}, {item["id"] for item in page["items"]})

    def test_date_filter_uses_shanghai_day(self) -> None:
        # UTC 16:30 = 上海次日 00:30，必须归到 11-09 而不是 11-08
        txn = self._insert_txn(occurred_at="2026-11-08T16:30:00+00:00", amount_fen=500)
        on_9th = self._list(date_from="2026-11-09", date_to="2026-11-09")
        on_8th = self._list(date_from="2026-11-08", date_to="2026-11-08")
        self.assertEqual([txn], [item["id"] for item in on_9th["items"]])
        self.assertEqual(0, on_8th["total"])

    def test_date_range_reversed_is_422(self) -> None:
        response = self.client.get(
            "/api/transactions", params={"date_from": "2026-11-10", "date_to": "2026-11-01"}
        )
        self.assertEqual(422, response.status_code)
        body = response.json()["error"]
        self.assertEqual("VALIDATION_ERROR", body["code"])
        self.assertEqual("DATE_RANGE_REVERSED", body["details"]["fields"][0]["code"])

    def test_filters_by_category_source_and_flow(self) -> None:
        dining = self._insert_txn(
            occurred_at="2026-11-08T10:00:00+08:00", amount_fen=100, category="dining"
        )
        transport = self._insert_txn(
            occurred_at="2026-11-08T11:00:00+08:00",
            amount_fen=200,
            category="transport",
            source="alipay",
        )
        salary = self._insert_txn(
            occurred_at="2026-11-08T12:00:00+08:00",
            amount_fen=300,
            flow_type="income",
            category="salary",
        )

        self.assertEqual(
            [dining], [i["id"] for i in self._list(category="dining")["items"]]
        )
        self.assertEqual(
            [transport], [i["id"] for i in self._list(source="alipay")["items"]]
        )
        self.assertEqual([salary], [i["id"] for i in self._list(flow_type="income")["items"]])
        self.assertEqual(3, self._list()["total"])

    def test_pagination_reports_total_before_slicing(self) -> None:
        for index in range(5):
            self._insert_txn(
                occurred_at=f"2026-11-0{index + 1}T10:00:00+08:00", amount_fen=100 + index
            )
        page1 = self._list(page=1, page_size=2)
        page3 = self._list(page=3, page_size=2)
        self.assertEqual(5, page1["total"])
        self.assertEqual(2, len(page1["items"]))
        self.assertEqual(1, len(page3["items"]))
        # 倒序：11-05(104), 11-04(103) | 11-03(102), 11-02(101) | 11-01(100)
        self.assertEqual(104, page1["items"][0]["amount_fen"])
        self.assertEqual(100, page3["items"][0]["amount_fen"])

    def test_page_size_over_100_is_422(self) -> None:
        response = self.client.get("/api/transactions", params={"page_size": 101})
        self.assertEqual(422, response.status_code)
        self.assertEqual("VALIDATION_ERROR", response.json()["error"]["code"])

    def test_unknown_category_filter_is_422(self) -> None:
        response = self.client.get("/api/transactions", params={"category": "grocery"})
        self.assertEqual(422, response.status_code)

    # ------------------------------------------------------------ 纠错接口

    def test_patch_category_marks_manual(self) -> None:
        txn = self._insert_txn(occurred_at="2026-11-08T12:00:00+08:00", amount_fen=2300)
        response = self._patch(
            txn, {"expected_version": 1, "changes": {"category": "shopping"}}
        )
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual("shopping", body["category"])
        self.assertEqual("manual", body["classification_source"])
        self.assertEqual(2, body["version"])

    def test_patch_without_category_keeps_source(self) -> None:
        txn = self._insert_txn(occurred_at="2026-11-08T12:00:00+08:00", amount_fen=2300)
        body = self._patch(
            txn,
            {
                "expected_version": 1,
                "changes": {"amount_fen": 2500, "merchant": "星巴克咖啡"},
            },
        ).json()
        self.assertEqual(2500, body["amount_fen"])
        self.assertEqual("星巴克咖啡", body["merchant"])
        # 没提交 category 就不能动分类来源，否则等于系统偷偷改判了分类
        self.assertEqual("general_rule", body["classification_source"])

    def test_patch_nothing_changed_keeps_version(self) -> None:
        txn = self._insert_txn(occurred_at="2026-11-08T12:00:00+08:00", amount_fen=2300)
        body = self._patch(
            txn, {"expected_version": 1, "changes": {"amount_fen": 2300}}
        ).json()
        # 值没变就不该 +1，否则并发编辑的乐观锁会被无意义地打乱
        self.assertEqual(1, body["version"])

    def test_patch_stale_version_conflicts(self) -> None:
        txn = self._insert_txn(occurred_at="2026-11-08T12:00:00+08:00", amount_fen=2300)
        self._patch(txn, {"expected_version": 1, "changes": {"category": "shopping"}})
        response = self._patch(txn, {"expected_version": 1, "changes": {"category": "other"}})
        self.assertEqual(409, response.status_code)
        body = response.json()["error"]
        self.assertEqual("VERSION_CONFLICT", body["code"])
        self.assertEqual(2, body["details"]["current_version"])

    def test_patch_other_users_transaction_is_404(self) -> None:
        other = f"ledger_other_{uuid.uuid4().hex[:8]}"
        _make_user(other)
        theirs = self._insert_txn(
            occurred_at="2026-11-08T12:00:00+08:00", amount_fen=2300, username=other
        )
        response = self._patch(
            theirs, {"expected_version": 1, "changes": {"category": "shopping"}}
        )
        # 403 会泄露"这个 ID 存在"，一律 404
        self.assertEqual(404, response.status_code)
        self.assertEqual("RESOURCE_NOT_FOUND", response.json()["error"]["code"])

    def test_patch_requires_csrf(self) -> None:
        txn = self._insert_txn(occurred_at="2026-11-08T12:00:00+08:00", amount_fen=2300)
        response = self._patch(
            txn, {"expected_version": 1, "changes": {"category": "shopping"}}, csrf=""
        )
        self.assertEqual(403, response.status_code)
        self.assertEqual("CSRF_INVALID", response.json()["error"]["code"])

    def test_patch_naive_time_is_422(self) -> None:
        txn = self._insert_txn(occurred_at="2026-11-08T12:00:00+08:00", amount_fen=2300)
        response = self._patch(
            txn,
            {"expected_version": 1, "changes": {"occurred_at": "2026-11-09T08:00:00"}},
        )
        self.assertEqual(422, response.status_code)
        self.assertEqual(
            "TIME_WITHOUT_TIMEZONE",
            response.json()["error"]["details"]["fields"][0]["code"],
        )

    def test_patch_remember_rule_creates_personal_rule(self) -> None:
        txn = self._insert_txn(
            occurred_at="2026-11-08T12:00:00+08:00",
            amount_fen=2300,
            merchant="瑞幸咖啡 深圳科技园店",
        )
        self._patch(
            txn,
            {
                "expected_version": 1,
                "changes": {"category": "dining"},
                "remember_rule": True,
            },
        )
        db = app.state.session_factory()
        try:
            rules = db.scalars(
                select(models.ClassificationRule).where(
                    models.ClassificationRule.user_id == self._user_id()
                )
            ).all()
            self.assertEqual(1, len(rules))
            self.assertTrue(rules[0].enabled)
        finally:
            db.close()

    def test_patch_remember_rule_skipped_for_blank_merchant(self) -> None:
        txn = self._insert_txn(occurred_at="2026-11-08T12:00:00+08:00", amount_fen=2300)
        response = self._patch(
            txn,
            {
                "expected_version": 1,
                "changes": {"merchant": "   ", "category": "dining"},
                "remember_rule": True,
            },
        )
        # 契约：只在非空商户时生效。这里静默跳过，不报错也不建空规则
        self.assertEqual(200, response.status_code, response.text)
        db = app.state.session_factory()
        try:
            count = len(
                db.scalars(
                    select(models.ClassificationRule).where(
                        models.ClassificationRule.user_id == self._user_id()
                    )
                ).all()
            )
            self.assertEqual(0, count)
        finally:
            db.close()

    def test_patch_writes_correction_log(self) -> None:
        txn = self._insert_txn(occurred_at="2026-11-08T12:00:00+08:00", amount_fen=2300)
        self._patch(txn, {"expected_version": 1, "changes": {"category": "shopping"}})
        db = app.state.session_factory()
        try:
            logs = db.scalars(
                select(models.CorrectionLog).where(models.CorrectionLog.transaction_id == txn)
            ).all()
            self.assertEqual(1, len(logs))
            self.assertFalse(logs[0].rule_created)
        finally:
            db.close()

    # ------------------------------------------------------------ 月报接口

    def test_monthly_totals_follow_agreed_口径(self) -> None:
        self._insert_txn(
            occurred_at="2026-11-02T09:00:00+08:00", amount_fen=10000, flow_type="income",
            category="salary",
        )
        self._insert_txn(occurred_at="2026-11-03T12:00:00+08:00", amount_fen=3000, category="dining")
        self._insert_txn(occurred_at="2026-11-04T12:00:00+08:00", amount_fen=1200, category="shopping")
        self._insert_txn(occurred_at="2026-11-05T12:00:00+08:00", amount_fen=500, flow_type="refund")
        # 转账与还款留在明细里，但不进消费支出
        self._insert_txn(
            occurred_at="2026-11-06T12:00:00+08:00", amount_fen=5000, flow_type="transfer",
            category="other",
        )
        self._insert_txn(
            occurred_at="2026-11-07T12:00:00+08:00", amount_fen=2000, flow_type="repayment",
            category="other",
        )

        totals = self._report("2026-11")["totals"]
        self.assertEqual(10000, totals["income_fen"])
        self.assertEqual(4200, totals["gross_expense_fen"])
        self.assertEqual(500, totals["refund_fen"])
        self.assertEqual(3700, totals["net_expense_fen"])
        # 差额 = 收入 - 毛支出 + 退款，不是账户余额
        self.assertEqual(6300, totals["balance_fen"])

    def test_monthly_expense_by_category_excludes_refund_only(self) -> None:
        self._insert_txn(occurred_at="2026-11-03T12:00:00+08:00", amount_fen=3000, category="dining")
        self._insert_txn(occurred_at="2026-11-04T12:00:00+08:00", amount_fen=1200, category="shopping")
        self._insert_txn(
            occurred_at="2026-11-05T12:00:00+08:00", amount_fen=500, flow_type="refund",
            category="dining",
        )
        items = self._report("2026-11")["expense_by_category"]
        # 饼图展示毛支出：退款单列，不从类别里扣
        self.assertEqual(
            [{"category": "dining", "amount_fen": 3000}, {"category": "shopping", "amount_fen": 1200}],
            items,
        )

    def test_monthly_daily_trend_covers_every_day(self) -> None:
        self._insert_txn(occurred_at="2026-11-08T12:00:00+08:00", amount_fen=4200, category="dining")
        trend = self._report("2026-11")["daily_trend"]
        self.assertEqual(30, len(trend))
        self.assertEqual("2026-11-01", trend[0]["date"])
        self.assertEqual("2026-11-30", trend[-1]["date"])
        day8 = next(item for item in trend if item["date"] == "2026-11-08")
        self.assertEqual(4200, day8["gross_expense_fen"])
        self.assertEqual(0, trend[0]["gross_expense_fen"])

    def test_monthly_empty_month_returns_zeroes(self) -> None:
        report = self._report("2026-02")
        self.assertEqual(0, report["totals"]["income_fen"])
        self.assertEqual(0, report["totals"]["gross_expense_fen"])
        self.assertEqual([], report["expense_by_category"])
        self.assertEqual([], report["budgets"])
        # 空月也要给完整日期序列，否则前端画折线会断
        self.assertEqual(28, len(report["daily_trend"]))

    def test_monthly_leap_february_has_29_days(self) -> None:
        self.assertEqual(29, len(self._report("2024-02")["daily_trend"]))

    def test_monthly_invalid_month_is_422(self) -> None:
        for bad in ("2026-13", "2026-1", "202611", ""):
            response = self.client.get("/api/reports/monthly", params={"month": bad})
            self.assertEqual(422, response.status_code, f"{bad} 应当被拒绝")

    def test_monthly_isolation(self) -> None:
        other = f"ledger_other_{uuid.uuid4().hex[:8]}"
        _make_user(other)
        self._insert_txn(
            occurred_at="2026-11-03T12:00:00+08:00", amount_fen=9999, username=other
        )
        self.assertEqual(0, self._report("2026-11")["totals"]["gross_expense_fen"])

    def test_patch_amount_changes_report_immediately(self) -> None:
        txn = self._insert_txn(occurred_at="2026-11-03T12:00:00+08:00", amount_fen=3000)
        self.assertEqual(3000, self._report("2026-11")["totals"]["gross_expense_fen"])
        self._patch(txn, {"expected_version": 1, "changes": {"amount_fen": 5000}})
        # 列表与月报必须同源：改完一笔，报表数字立刻变，不需要清缓存
        self.assertEqual(5000, self._report("2026-11")["totals"]["gross_expense_fen"])

    def test_patch_month_moves_record_between_reports(self) -> None:
        txn = self._insert_txn(occurred_at="2026-11-30T23:00:00+08:00", amount_fen=2500)
        self._patch(
            txn,
            {
                "expected_version": 1,
                "changes": {"occurred_at": "2026-12-01T01:00:00+08:00"},
            },
        )
        self.assertEqual(0, self._report("2026-11")["totals"]["gross_expense_fen"])
        self.assertEqual(2500, self._report("2026-12")["totals"]["gross_expense_fen"])

    # ------------------------------------------------------------ 预算接口

    def test_put_budget_creates_and_overwrites(self) -> None:
        created = self._put_budget("2026-11", "dining", 20000)
        self.assertEqual(200, created.status_code, created.text)
        first = created.json()
        self.assertEqual(20000, first["amount_fen"])

        again = self._put_budget("2026-11", "dining", 30000)
        self.assertEqual(200, again.status_code)
        # 同（用户, 月份, 类别）覆盖而不是新建，ID 不变
        self.assertEqual(first["id"], again.json()["id"])
        self.assertEqual(30000, again.json()["amount_fen"])

        db = app.state.session_factory()
        try:
            count = len(
                db.scalars(
                    select(models.Budget).where(models.Budget.user_id == self._user_id())
                ).all()
            )
            self.assertEqual(1, count)
        finally:
            db.close()

    def test_put_budget_rejects_pending_category(self) -> None:
        response = self._put_budget("2026-11", "pending", 100)
        self.assertEqual(422, response.status_code)
        self.assertEqual("VALIDATION_ERROR", response.json()["error"]["code"])

    def test_put_budget_rejects_negative_amount(self) -> None:
        response = self._put_budget("2026-11", "dining", -1)
        self.assertEqual(422, response.status_code)

    def test_put_budget_accepts_zero(self) -> None:
        response = self._put_budget("2026-11", "dining", 0)
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual(0, response.json()["amount_fen"])

    def test_put_budget_requires_csrf(self) -> None:
        response = self.client.put(
            "/api/budgets",
            json={"month": "2026-11", "category": "dining", "amount_fen": 100},
        )
        self.assertEqual(403, response.status_code)
        self.assertEqual("CSRF_INVALID", response.json()["error"]["code"])

    def test_budget_status_uses_net_expense(self) -> None:
        self._insert_txn(occurred_at="2026-11-03T12:00:00+08:00", amount_fen=2500, category="dining")
        self._insert_txn(
            occurred_at="2026-11-05T12:00:00+08:00", amount_fen=500, flow_type="refund",
            category="dining",
        )
        self._put_budget("2026-11", "dining", 2000)

        status = self._report("2026-11")["budgets"][0]
        # 退款要回到预算里：净支出 2000，正好花完而不是超支
        self.assertEqual(2000, status["spent_fen"])
        self.assertEqual(0, status["remaining_fen"])
        self.assertEqual(0, status["over_fen"])

    def test_budget_overage_reported(self) -> None:
        self._insert_txn(occurred_at="2026-11-03T12:00:00+08:00", amount_fen=2500, category="dining")
        self._put_budget("2026-11", "dining", 2000)
        status = self._report("2026-11")["budgets"][0]
        self.assertEqual(2500, status["spent_fen"])
        self.assertEqual(-500, status["remaining_fen"])
        self.assertEqual(500, status["over_fen"])

    def test_budget_is_scoped_to_month_and_user(self) -> None:
        self._put_budget("2026-11", "dining", 20000)
        self.assertEqual([], self._report("2026-12")["budgets"])

        other = f"ledger_other_{uuid.uuid4().hex[:8]}"
        _make_user(other)
        self.client.post("/api/auth/logout", headers={"X-CSRF-Token": self.csrf})
        self._login(other)
        self.assertEqual([], self._report("2026-11")["budgets"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
