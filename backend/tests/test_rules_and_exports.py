"""个人规则（listRules / patchRule）与导出（CSV / PDF）的端到端测试。

重点不是"接口返回 200"，而是钉住四件容易出鬼故事的事：

1. **A07 的完整四步**：改正 → 记住商户 → 新交易自动命中 → 停用后不再命中。
   这是闭环第五环（用户修正反馈）的验收线，缺任何一步都是假闭合。
2. **停用不改历史**：规则停用只影响后续分类，已入账交易的类别必须原样。
3. **CSV 防公式注入**：商户名以 `=` `+` `-` `@` 开头时，Excel 会当公式执行。
   导出必须前置单引号，否则一个商户名就能在别人机器上跑命令。
4. **导出范围 = 列表范围**：同一组筛选条件，CSV 行数必须等于列表 total，
   不允许"页面 12 条、导出 15 条"。

运行（在 backend/ 目录）：
    python -m unittest tests.test_rules_and_exports -v
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

_TMP_DIR = tempfile.mkdtemp(prefix="mbl_rules_test_")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault(
    "DATABASE_URL", f"sqlite+pysqlite:///{Path(_TMP_DIR, 'rules.db').as_posix()}"
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
from app.services import exporting  # noqa: E402
from app.services.dedupe import month_index  # noqa: E402

PASSWORD = "rules-pass-2026"

_TXN_FIELDS = (
    "source_transaction_id",
    "occurred_at",
    "amount_fen",
    "currency",
    "flow_type",
    "merchant",
    "description",
    "category",
)

# 微信导出格式的表头与首尾行，字段顺序照真实导出文件
_WECHAT_HEAD = (
    "微信支付账单明细,,,,,,,,,,\n"
    "微信昵称：[test],,,,,,,,,,\n"
    "起始时间：[2026-11-01 00:00:00] 终止时间：[2026-11-30 23:59:59],,,,,,,,,,\n"
    "导出类型：[全部],,,,,,,,,,\n"
    "导出时间：[2026-12-01 10:00:00],,,,,,,,,,\n"
    "共1笔记录,,,,,,,,,,\n"
    "----------------------微信支付账单明细列表--------------------,,,,,,,,,,\n"
    "交易时间,交易类型,交易对方,商品,收/支,金额(元),支付方式,当前状态,交易单号\n"
)
_WECHAT_TAIL = "----------------------以上是全部记录--------------------,,,,,,,,,,\n"


def _wechat_csv(rows: list[tuple[str, str, str]]) -> bytes:
    """按 (时间, 商户, 订单号) 生成一份最小的微信格式账单。"""
    body = "".join(
        f"{when},商户消费,{merchant},测试商品,支出,¥35.00,零钱,支付成功,{order}\n"
        for when, merchant, order in rows
    )
    return ("\ufeff" + _WECHAT_HEAD + body + _WECHAT_TAIL).encode("utf-8")


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


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Base.metadata.create_all(app.state.engine)

    def setUp(self) -> None:
        self.username = f"rules_{uuid.uuid4().hex[:12]}"
        _make_user(self.username)
        self.client = TestClient(app)
        # with 进入才会启动 lifespan 里的批次执行器，上传链路才能跑
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
            assert user is not None
            return user.id
        finally:
            db.close()

    def _insert_rule(
        self,
        *,
        merchant: str,
        category: str,
        source: str = "wechat",
        enabled: bool = True,
        username: str | None = None,
    ) -> str:
        record = models.ClassificationRule(
            id=str(uuid.uuid4()),
            user_id=self._user_id(username),
            source=source,
            version=1,
            enabled=enabled,
            encrypted_payload=encrypt_json(
                _key(),
                {"merchant_normalized": merchant, "category": category, "enabled": enabled},
            ),
        )
        db = app.state.session_factory()
        try:
            db.add(record)
            db.commit()
            return record.id
        finally:
            db.close()

    def _insert_txn(
        self,
        *,
        occurred_at: str,
        amount_fen: int,
        merchant: str = "测试商户",
        category: str = "dining",
        flow_type: str = "expense",
        source: str = "wechat",
        username: str | None = None,
        description: str = "",
    ) -> str:
        payload = {
            "source_transaction_id": None,
            "occurred_at": occurred_at,
            "amount_fen": amount_fen,
            "currency": "CNY",
            "flow_type": flow_type,
            "merchant": merchant,
            "description": description,
            "category": category,
            "ingestion_method": "file",
            "classification_source": "general_rule",
            "classification_reason": "命中通用规则",
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

    def _rules(self) -> list[dict]:
        response = self.client.get("/api/classification-rules")
        self.assertEqual(200, response.status_code, response.text)
        return response.json()["items"]

    def _patch_rule(self, rule_id: str, body: dict, csrf: str | None = None):
        return self.client.patch(
            f"/api/classification-rules/{rule_id}",
            json=body,
            headers={"X-CSRF-Token": self.csrf if csrf is None else csrf},
        )

    # 导入链路

    def _upload(self, data: bytes, csrf: str | None = None):
        return self.client.post(
            "/api/imports",
            data={"source": "wechat", "ingestion_method": "file"},
            files={"file": ("wechat.csv", data, "application/octet-stream")},
            headers={"X-CSRF-Token": csrf or self.csrf},
        )

    def _pending_batch(self, data: bytes) -> dict:
        created = self._upload(data)
        self.assertEqual(202, created.status_code, created.text)
        batch_id = created.json()["id"]
        deadline = time.monotonic() + 20
        batch: dict = {}
        while time.monotonic() < deadline:
            response = self.client.get(f"/api/imports/{batch_id}")
            self.assertEqual(200, response.status_code, response.text)
            batch = response.json()
            if batch["status"] in {"pending_review", "failed"}:
                return batch
            time.sleep(0.02)
        self.fail(f"批次未在超时内完成，当前 {batch.get('status')}")

    def _confirm_all(self, batch: dict) -> dict:
        payload = {
            "request_id": str(uuid.uuid4()),
            "expected_version": batch["version"],
            "rows": [
                {
                    "row_id": draft["row_id"],
                    "transaction": {field: draft[field] for field in _TXN_FIELDS},
                    "allow_suspected_duplicate": False,
                }
                for draft in batch["rows"]
            ],
        }
        response = self.client.post(
            f"/api/imports/{batch['id']}/confirm",
            json=payload,
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(200, response.status_code, response.text)
        return response.json()


class RulesApiTest(_Base):
    def test_list_rules_empty(self) -> None:
        self.assertEqual([], self._rules())

    def test_list_rules_includes_disabled_and_sorted(self) -> None:
        # 契约：返回本人全部规则（含已停用），按 source 再 merchant_normalized 升序
        self._insert_rule(merchant="b商户", category="dining")
        self._insert_rule(merchant="a商户", category="transport")
        self._insert_rule(merchant="c商户", category="shopping", enabled=False)
        self._insert_rule(merchant="a商户", category="other", source="alipay")

        items = self._rules()
        self.assertEqual(4, len(items))
        seen = [(item["source"], item["merchant_normalized"]) for item in items]
        self.assertEqual(
            [
                ("alipay", "a商户"),
                ("wechat", "a商户"),
                ("wechat", "b商户"),
                ("wechat", "c商户"),
            ],
            seen,
        )
        # 停用的要在列表里看得见，否则用户无法重新启用
        disabled = [item for item in items if not item["enabled"]]
        self.assertEqual(1, len(disabled))
        self.assertEqual("c商户", disabled[0]["merchant_normalized"])

    def test_list_rules_isolated_between_users(self) -> None:
        other = f"other_{uuid.uuid4().hex[:10]}"
        _make_user(other)
        self._insert_rule(merchant="我的商户", category="dining")
        self._insert_rule(merchant="别人的商户", category="dining", username=other)

        self.assertEqual(
            ["我的商户"], [item["merchant_normalized"] for item in self._rules()]
        )

    def test_patch_rule_disable_and_reenable(self) -> None:
        rule_id = self._insert_rule(merchant="瑞幸咖啡", category="dining")

        disabled = self._patch_rule(rule_id, {"expected_version": 1, "enabled": False})
        self.assertEqual(200, disabled.status_code, disabled.text)
        self.assertFalse(disabled.json()["enabled"])
        self.assertEqual(2, disabled.json()["version"])

        enabled = self._patch_rule(rule_id, {"expected_version": 2, "enabled": True})
        self.assertEqual(200, enabled.status_code, enabled.text)
        self.assertTrue(enabled.json()["enabled"])
        self.assertEqual(3, enabled.json()["version"])

    def test_patch_rule_change_category(self) -> None:
        rule_id = self._insert_rule(merchant="某商户", category="dining")
        response = self._patch_rule(
            rule_id, {"expected_version": 1, "category": "transport"}
        )
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("transport", response.json()["category"])
        self.assertEqual("transport", self._rules()[0]["category"])

    def test_patch_rule_rejects_empty_payload(self) -> None:
        # 契约用 anyOf 要求至少给 enabled 或 category；pydantic 允许都为 None，
        # 这条约束必须由服务层补上，不能让空请求"悄悄成功"
        rule_id = self._insert_rule(merchant="某商户", category="dining")
        response = self._patch_rule(rule_id, {"expected_version": 1})
        self.assertEqual(422, response.status_code, response.text)
        self.assertEqual("VALIDATION_ERROR", response.json()["error"]["code"])
        self.assertEqual(
            "RULE_PATCH_EMPTY",
            response.json()["error"]["details"]["fields"][0]["code"],
        )

    def test_patch_rule_rejects_pending_category(self) -> None:
        # ResolvedCategory 不接受 pending
        rule_id = self._insert_rule(merchant="某商户", category="dining")
        response = self._patch_rule(
            rule_id, {"expected_version": 1, "category": "pending"}
        )
        self.assertEqual(422, response.status_code, response.text)

    def test_patch_rule_version_conflict(self) -> None:
        rule_id = self._insert_rule(merchant="某商户", category="dining")
        self._patch_rule(rule_id, {"expected_version": 1, "enabled": False})

        stale = self._patch_rule(rule_id, {"expected_version": 1, "enabled": True})
        self.assertEqual(409, stale.status_code, stale.text)
        error = stale.json()["error"]
        self.assertEqual("VERSION_CONFLICT", error["code"])
        self.assertEqual(2, error["details"]["current_version"])

    def test_patch_rule_other_user_gets_404(self) -> None:
        other = f"other_{uuid.uuid4().hex[:10]}"
        _make_user(other)
        rule_id = self._insert_rule(merchant="别人的", category="dining", username=other)
        response = self._patch_rule(rule_id, {"expected_version": 1, "enabled": False})
        # 别人的规则一律 404：403 会泄露"这个 ID 存在"
        self.assertEqual(404, response.status_code, response.text)
        self.assertEqual("RESOURCE_NOT_FOUND", response.json()["error"]["code"])

    def test_patch_rule_requires_csrf(self) -> None:
        rule_id = self._insert_rule(merchant="某商户", category="dining")
        response = self._patch_rule(
            rule_id, {"expected_version": 1, "enabled": False}, csrf="wrong-token"
        )
        self.assertEqual(403, response.status_code, response.text)
        self.assertEqual("CSRF_INVALID", response.json()["error"]["code"])

    def test_disable_rule_does_not_rewrite_history(self) -> None:
        """停用只影响后续分类，已经入账的交易必须原样保留。"""
        txn_id = self._insert_txn(
            occurred_at="2026-11-05T12:00:00+08:00", amount_fen=2300, category="dining"
        )
        rule_id = self._insert_rule(merchant="测试商户", category="dining")
        self._patch_rule(rule_id, {"expected_version": 1, "enabled": False})

        page = self.client.get("/api/transactions").json()
        target = next(item for item in page["items"] if item["id"] == txn_id)
        self.assertEqual("dining", target["category"])
        self.assertEqual(1, target["version"])


class FeedbackLoopTest(_Base):
    """docs/08 A07：改正 → 记住商户 → 新交易命中 → 停用后不再命中。"""

    def test_a07_full_loop(self) -> None:
        # ---- 第一步：导入一笔，通用规则把它分到 dining（"瑞幸"命中餐饮关键词）
        first = self._pending_batch(
            _wechat_csv([("2026-11-05 09:10:00", "瑞幸咖啡", "ORDER-A-001")])
        )
        self.assertEqual("pending_review", first["status"], first.get("issues"))
        self.assertEqual("dining", first["rows"][0]["category"])
        self.assertEqual("general_rule", first["rows"][0]["classification_source"])
        self._confirm_all(first)

        txn = self.client.get("/api/transactions").json()["items"][0]

        # ---- 第二步：用户改成 transport，并勾"记住商户"
        patched = self.client.patch(
            f"/api/transactions/{txn['id']}",
            json={
                "expected_version": txn["version"],
                "changes": {"category": "transport"},
                "remember_rule": True,
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(200, patched.status_code, patched.text)
        self.assertEqual("transport", patched.json()["category"])
        self.assertEqual("manual", patched.json()["classification_source"])

        rules = self._rules()
        self.assertEqual(1, len(rules))
        self.assertEqual("transport", rules[0]["category"])
        self.assertTrue(rules[0]["enabled"])

        # ---- 第三步：再导入一笔同商户的新交易，必须命中个人规则
        second = self._pending_batch(
            _wechat_csv([("2026-11-18 19:20:00", "瑞幸咖啡", "ORDER-A-002")])
        )
        self.assertEqual("pending_review", second["status"], second.get("issues"))
        self.assertEqual("transport", second["rows"][0]["category"])
        self.assertEqual("user_rule", second["rows"][0]["classification_source"])
        self._confirm_all(second)

        # ---- 第四步：停用规则，第三笔应退回通用规则（dining 而不是 transport）
        rule_id = self._rules()[0]["id"]
        disabled = self._patch_rule(
            rule_id, {"expected_version": self._rules()[0]["version"], "enabled": False}
        )
        self.assertEqual(200, disabled.status_code, disabled.text)

        third = self._pending_batch(
            _wechat_csv([("2026-11-19 08:00:00", "瑞幸咖啡", "ORDER-A-003")])
        )
        self.assertEqual("pending_review", third["status"], third.get("issues"))
        self.assertEqual("dining", third["rows"][0]["category"])
        self.assertEqual("general_rule", third["rows"][0]["classification_source"])
        self._confirm_all(third)

        # 三笔都已入账：第一笔被用户改成 transport，第二笔命中规则成 transport，
        # 第三笔在停用后按通用规则成 dining。停用不回溯改前两笔——这就是
        # 契约"停用不重写历史交易"的实际含义。
        page = self.client.get("/api/transactions").json()
        categories = sorted(item["category"] for item in page["items"])
        self.assertEqual(["dining", "transport", "transport"], categories)


class ExportCsvTest(_Base):
    def _export(self, **params):
        return self.client.get("/api/exports/transactions.csv", params=params)

    def test_export_csv_headers_and_rows(self) -> None:
        self._insert_txn(occurred_at="2026-11-05T12:00:00+08:00", amount_fen=2300)
        self._insert_txn(
            occurred_at="2026-11-06T12:00:00+08:00",
            amount_fen=9900,
            flow_type="income",
            category="salary",
            merchant="某公司",
        )

        response = self._export()
        self.assertEqual(200, response.status_code, response.text)
        self.assertIn("text/csv", response.headers["content-type"])
        self.assertIn("attachment;", response.headers["content-disposition"])
        # RFC 5987：中文文件名必须给 filename*
        self.assertIn("filename*=UTF-8''", response.headers["content-disposition"])

        body = response.content
        self.assertTrue(body.startswith(b"\xef\xbb\xbf"), "应有 UTF-8 BOM 便于 Excel 打开")
        text = body.decode("utf-8-sig")
        lines = text.strip().split("\r\n")
        self.assertEqual(3, len(lines))  # 表头 + 2 行
        self.assertEqual(
            list(exporting.CSV_COLUMNS), lines[0].split(",")
        )
        # 金额是整数分，且列名明确 amount_fen
        self.assertIn("amount_fen", lines[0])
        self.assertIn("2300", text)
        self.assertIn("9900", text)

    def test_export_csv_range_matches_list(self) -> None:
        for day in range(1, 6):
            self._insert_txn(
                occurred_at=f"2026-11-0{day}T12:00:00+08:00", amount_fen=100 * day
            )
        params = {"date_from": "2026-11-02", "date_to": "2026-11-04"}

        listed = self.client.get("/api/transactions", params=params).json()
        exported = self._export(**params)
        text = exported.content.decode("utf-8-sig").strip().split("\r\n")

        self.assertEqual(3, listed["total"])
        # 导出范围必须与列表 total 一致（A11）
        self.assertEqual(listed["total"] + 1, len(text))

    def test_export_csv_ignores_pagination(self) -> None:
        for day in range(1, 4):
            self._insert_txn(
                occurred_at=f"2026-11-0{day}T12:00:00+08:00", amount_fen=100
            )
        # 契约："导出所有筛选结果，不限当前分页，不接受 page/page_size"
        response = self._export(page=1, page_size=1)
        self.assertEqual(200, response.status_code, response.text)
        lines = response.content.decode("utf-8-sig").strip().split("\r\n")
        self.assertEqual(4, len(lines))  # 表头 + 3 行，没被 page_size 截断

    def test_export_csv_blocks_formula_injection(self) -> None:
        """商户名以 = + - @ 开头时，Excel 会当公式执行，必须前置单引号。"""
        nasty = [
            ("=1+1", "=1+1"),
            ("+SUM(A1)", "+SUM(A1)"),
            ("-2+3", "-2+3"),
            ("@SUM(1)", "@SUM(1)"),
        ]
        for index, (merchant, _) in enumerate(nasty):
            self._insert_txn(
                occurred_at=f"2026-11-0{index + 1}T12:00:00+08:00",
                amount_fen=100,
                merchant=merchant,
            )

        text = self._export().content.decode("utf-8-sig")
        for merchant, _ in nasty:
            self.assertIn(f"' {merchant}".replace(" ", ""), text.replace(" ", ""))

        # 正常商户不能被误加单引号
        self._insert_txn(
            occurred_at="2026-11-09T12:00:00+08:00", amount_fen=100, merchant="永辉超市"
        )
        text = self._export().content.decode("utf-8-sig")
        self.assertIn("永辉超市", text)
        self.assertNotIn("'永辉超市", text)

    def test_export_csv_isolated_between_users(self) -> None:
        other = f"other_{uuid.uuid4().hex[:10]}"
        _make_user(other)
        self._insert_txn(
            occurred_at="2026-11-05T12:00:00+08:00", amount_fen=111, username=other,
            merchant="别人的商户",
        )
        self._insert_txn(
            occurred_at="2026-11-05T12:00:00+08:00", amount_fen=222, merchant="我的商户"
        )
        text = self._export().content.decode("utf-8-sig")
        self.assertIn("我的商户", text)
        self.assertNotIn("别人的商户", text)
        self.assertNotIn("111", text)

    def test_export_csv_reversed_range_422(self) -> None:
        response = self._export(date_from="2026-11-10", date_to="2026-11-01")
        self.assertEqual(422, response.status_code, response.text)
        self.assertEqual("VALIDATION_ERROR", response.json()["error"]["code"])
        self.assertEqual(
            "DATE_RANGE_REVERSED",
            response.json()["error"]["details"]["fields"][0]["code"],
        )

    def test_export_csv_requires_login(self) -> None:
        anonymous = TestClient(app)
        response = anonymous.get("/api/exports/transactions.csv")
        self.assertEqual(401, response.status_code, response.text)
        self.assertEqual("AUTH_REQUIRED", response.json()["error"]["code"])


class ExportPdfTest(_Base):
    def test_export_pdf_bytes(self) -> None:
        self._insert_txn(
            occurred_at="2026-11-05T12:00:00+08:00", amount_fen=3500, category="dining"
        )
        self._insert_txn(
            occurred_at="2026-11-06T12:00:00+08:00",
            amount_fen=10000,
            flow_type="income",
            category="salary",
        )

        response = self.client.get(
            "/api/exports/monthly.pdf", params={"month": "2026-11"}
        )
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("application/pdf", response.headers["content-type"])
        self.assertIn("filename*=UTF-8''", response.headers["content-disposition"])
        self.assertTrue(response.content.startswith(b"%PDF-"))
        # 真嵌了字体才会有 FontFile2；没有就说明中文是方块
        self.assertIn(b"FontFile2", response.content)
        self.assertGreater(len(response.content), 2000)

    def test_export_pdf_empty_month_still_renders(self) -> None:
        response = self.client.get(
            "/api/exports/monthly.pdf", params={"month": "2026-01"}
        )
        self.assertEqual(200, response.status_code, response.text)
        self.assertTrue(response.content.startswith(b"%PDF-"))

    def test_export_pdf_isolated_between_users(self) -> None:
        other = f"other_{uuid.uuid4().hex[:10]}"
        _make_user(other)
        self._insert_txn(
            occurred_at="2026-11-05T12:00:00+08:00", amount_fen=777700, username=other
        )
        response = self.client.get(
            "/api/exports/monthly.pdf", params={"month": "2026-11"}
        )
        self.assertEqual(200, response.status_code, response.text)
        # 别人的 7777 元不能出现在我的月报里（PDF 里数字是文本流，仍能搜到明文）
        for stream_ in _pdf_text_blobs(response.content):
            self.assertNotIn("7777.00", stream_)

    def test_export_pdf_unavailable_when_no_font(self) -> None:
        """字体缺失时如实 503，不能输出一份中文全是方块的 PDF 冒充成功。"""
        exporting._font_state.update({"key": None, "name": None})
        with patch.object(exporting, "_FONT_CANDIDATES", ()):
            response = self.client.get(
                "/api/exports/monthly.pdf", params={"month": "2026-11"}
            )
        exporting._font_state.update({"key": None, "name": None})

        self.assertEqual(503, response.status_code, response.text)
        self.assertEqual("EXPORT_UNAVAILABLE", response.json()["error"]["code"])

    def test_export_pdf_rejects_bad_month(self) -> None:
        response = self.client.get(
            "/api/exports/monthly.pdf", params={"month": "2026-13"}
        )
        self.assertEqual(422, response.status_code, response.text)
        self.assertEqual("VALIDATION_ERROR", response.json()["error"]["code"])


def _pdf_text_blobs(data: bytes) -> list[str]:
    """把 PDF 里可能含文本的分支解出来（Flate 压缩的 content stream）。

    不引第三方库：只用来断言"别人的金额没混进来"，不需要完整解析。
    """
    import re
    import zlib

    blobs: list[str] = []
    blobs.append(data.decode("latin-1"))
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        try:
            blobs.append(zlib.decompress(match.group(1)).decode("latin-1"))
        except zlib.error:
            continue
    return blobs


if __name__ == "__main__":
    unittest.main()
