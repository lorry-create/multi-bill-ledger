"""T02 导入中心端到端测试：上传 → 轮询 → 重试 → 确认入账。

覆盖的是**契约与业务规则**，不是"当前实现碰巧返回什么"：
- 401/403/413/415/422/404/409 的边界，逐条对应 docs/19 第八节的可勾验收清单；
- 状态机走到 `pending_review` 才允许确认；
- 确认的幂等（同 ID 同体重放 / 同 ID 异体 409 / 已完成新 ID 409）、乐观锁、去重；
- 重复上传同一份账单不会二次入账。

运行（在 backend/ 目录）：
    python -m unittest tests.test_imports_api -v

注意：本模块**必须**早于其它测试模块导入（字母序已满足），因为它用环境变量把
上传上限调小到 512KiB/128KiB。否则 10MiB 的 413 用例要现造 11MiB 数据，测试会慢到没人愿意跑。
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
import uuid
from datetime import timedelta
from pathlib import Path

TMP_DIR = tempfile.mkdtemp(prefix="mbl_imports_test_")
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{Path(TMP_DIR, 'imports.db').as_posix()}"
os.environ["SESSION_SECRET"] = "test-session-secret-not-for-production"
os.environ["DATA_ENCRYPTION_KEY"] = "test-data-key-not-for-production"
os.environ["COOKIE_SECURE"] = "0"
os.environ["UPLOAD_MAX_FILE_BYTES"] = str(512 * 1024)
os.environ["UPLOAD_MAX_IMAGE_BYTES"] = str(128 * 1024)
os.environ["IMPORT_WORKER_POLL_SECONDS"] = "0.02"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app import models  # noqa: E402
from app.contracts import CONTRACT_VERSION  # noqa: E402
from app.crypto import decrypt_json, encrypt_json  # noqa: E402
from app.db import Base, utcnow  # noqa: E402
from app.main import app  # noqa: E402
from app.security import hash_password  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "real_format_samples"
WECHAT_SAMPLE = (FIXTURES / "wechat_export_sample.csv").read_bytes()
WECHAT_NAME = "wechat_export_sample.csv"

OTHER = "import_other"
PASSWORD = "import-pass-2026"

# 契约里 Batch.rows 的字段，用来构造确认请求（TransactionInput 是它的子集）
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


def _make_user(username: str) -> None:
    factory = app.state.session_factory
    db = factory()
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


class ImportApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Base.metadata.create_all(app.state.engine)
        _make_user(OTHER)

    def setUp(self) -> None:
        # 每个用例独立账号：用例之间共享库，同一份账单会被反复确认，
        # 不隔离的话第二个用例开始所有行都是 duplicate，断言全部失真
        self.username = f"import_{uuid.uuid4().hex[:12]}"
        _make_user(self.username)
        # 用 with 进入：lifespan 才会启动批次执行器（后台 worker）
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

    def _upload(self, data: bytes = WECHAT_SAMPLE, name: str = WECHAT_NAME,
                source: str = "wechat", method: str = "file", csrf: str | None = None):
        return self.client.post(
            "/api/imports",
            data={"source": source, "ingestion_method": method},
            files={"file": (name, data, "application/octet-stream")},
            headers={"X-CSRF-Token": csrf or self.csrf},
        )

    def _upload_ok(self, **kwargs) -> dict:
        response = self._upload(**kwargs)
        self.assertEqual(202, response.status_code, response.text)
        return response.json()

    def _wait_status(self, batch_id: str, wanted: set[str], timeout: float = 15.0) -> dict:
        deadline = time.monotonic() + timeout
        batch = {}
        while time.monotonic() < deadline:
            response = self.client.get(f"/api/imports/{batch_id}")
            self.assertEqual(200, response.status_code, response.text)
            batch = response.json()
            if batch["status"] in wanted:
                return batch
            time.sleep(0.02)
        self.fail(f"批次 {batch_id} 在 {timeout}s 内没有到达 {wanted}，当前 {batch.get('status')}")

    def _pending_batch(self, **kwargs) -> dict:
        created = self._upload_ok(**kwargs)
        return self._wait_status(created["id"], {"pending_review", "failed"})

    def _confirm_payload(self, batch: dict, *, request_id: str | None = None,
                         expected_version: int | None = None, allow_suspected: bool = False,
                         limit: int | None = None) -> dict:
        rows = batch["rows"] if limit is None else batch["rows"][:limit]
        return {
            "request_id": request_id or str(uuid.uuid4()),
            "expected_version": batch["version"] if expected_version is None else expected_version,
            "rows": [
                {
                    "row_id": draft["row_id"],
                    "transaction": {field: draft[field] for field in _TXN_FIELDS},
                    "allow_suspected_duplicate": allow_suspected,
                }
                for draft in rows
            ],
        }

    def _confirm(self, batch_id: str, payload: dict, csrf: str | None = None):
        return self.client.post(
            f"/api/imports/{batch_id}/confirm",
            json=payload,
            headers={"X-CSRF-Token": csrf or self.csrf},
        )

    def _batch_row(self, batch_id: str) -> models.ImportBatch:
        db = app.state.session_factory()
        try:
            return db.get(models.ImportBatch, batch_id)
        finally:
            db.close()

    def _txn_count(self, username: str | None = None) -> int:
        username = username or self.username
        db = app.state.session_factory()
        try:
            user = db.scalar(select(models.User).where(models.User.username == username))
            return db.scalar(
                select(func.count())
                .select_from(models.Transaction)
                .where(models.Transaction.user_id == user.id)
            )
        finally:
            db.close()

    # ---------------------------------------------------------------- 认证

    def test_read_endpoints_require_session(self) -> None:
        anonymous = TestClient(app)
        for path in ("/api/imports/whatever", "/api/imports/whatever/original"):
            response = anonymous.get(path)
            self.assertEqual(401, response.status_code, path)
            self.assertIn("error", response.json())
        anonymous.close()

    def test_confirm_requires_csrf(self) -> None:
        batch = self._pending_batch()
        payload = self._confirm_payload(batch)
        response = self.client.post(
            f"/api/imports/{batch['id']}/confirm", json=payload
        )
        self.assertEqual(403, response.status_code)
        self.assertEqual("CSRF_TOKEN_INVALID", response.json()["error"]["code"])

    # ---------------------------------------------------------------- 上传校验

    def test_upload_returns_202_with_location_and_retry_after(self) -> None:
        response = self._upload()
        self.assertEqual(202, response.status_code, response.text)
        self.assertEqual(CONTRACT_VERSION, response.headers.get("X-Contract-Version"))
        batch = response.json()
        self.assertEqual(f"/api/imports/{batch['id']}", response.headers.get("location"))
        self.assertEqual("1", response.headers.get("retry-after"))
        # 上传只建批次：不同步返回草稿，也不自动入账
        self.assertIn(batch["status"], {"uploaded", "processing"})
        self.assertEqual([], batch["rows"])
        self.assertIsNone(batch["progress"]["total"])
        self.assertEqual(WECHAT_NAME, batch["file_name"])
        self.assertEqual(1, batch["version"])

    def test_upload_rejects_oversize(self) -> None:
        # 上限被环境变量压到 512KiB；多 1KiB 就该 413，而不是读满内存再报错
        response = self._upload(data=b"a,b\n" + b"x" * (513 * 1024), name="big.csv")
        self.assertEqual(413, response.status_code, response.text)
        self.assertEqual("UPLOAD_TOO_LARGE", response.json()["error"]["code"])

    def test_upload_rejects_unsupported_extension(self) -> None:
        response = self._upload(data=b"%PDF-1.7 fake", name="bill.pdf")
        self.assertEqual(415, response.status_code, response.text)
        self.assertEqual("UNSUPPORTED_MEDIA_TYPE", response.json()["error"]["code"])

    def test_upload_rejects_binary_renamed_as_csv(self) -> None:
        """扩展名骗人：真正的 PDF 改名 .csv，要靠魔数拦住。"""
        response = self._upload(data=b"%PDF-1.7\n\x00\x01\x02binary", name="bill.csv")
        self.assertEqual(415, response.status_code, response.text)

    def test_upload_rejects_empty_file(self) -> None:
        response = self._upload(data=b"", name="empty.csv")
        self.assertEqual(422, response.status_code, response.text)
        body = response.json()["error"]
        self.assertEqual("VALIDATION_ERROR", body["code"])
        self.assertEqual("EMPTY_FILE", body["details"]["fields"][0]["code"])

    def test_upload_rejects_image_when_method_is_file(self) -> None:
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        response = self._upload(data=png, name="shot.png")
        self.assertEqual(415, response.status_code, response.text)

    def test_upload_rejects_invalid_source(self) -> None:
        response = self._upload(source="paypal")
        self.assertEqual(422, response.status_code, response.text)
        self.assertEqual("VALIDATION_FAILED", response.json()["error"]["code"])

    # ---------------------------------------------------------------- 处理与读取

    def test_batch_reaches_pending_review_with_drafts(self) -> None:
        batch = self._pending_batch()
        self.assertEqual("pending_review", batch["status"], batch.get("issues"))
        self.assertEqual(6, len(batch["rows"]))
        self.assertEqual(6, batch["progress"]["current"])
        self.assertEqual(6, batch["progress"]["total"])
        self.assertGreaterEqual(batch["version"], 2)

        by_merchant = {row["merchant"]: row for row in batch["rows"]}
        self.assertEqual("dining", by_merchant["星巴克咖啡"]["category"])
        self.assertEqual("transport", by_merchant["滴滴出行"]["category"])
        self.assertEqual("shopping", by_merchant["京东商城"]["category"])
        # 分类来源必须说实话：纯规则就是 general_rule，不许冒充 deepseek
        self.assertEqual(
            "general_rule", by_merchant["星巴克咖啡"]["classification_source"]
        )
        self.assertEqual(3500, by_merchant["星巴克咖啡"]["amount_fen"])
        # 收入 + 红包 → other，不能算成工资
        self.assertEqual("other", by_merchant["好友转入"]["category"])
        self.assertEqual("unique", by_merchant["星巴克咖啡"]["duplicate_status"])

    def test_batch_is_scoped_to_owner(self) -> None:
        batch = self._pending_batch()
        other_client = TestClient(app)
        other_client.__enter__()
        try:
            other_client.post(
                "/api/auth/login", json={"username": OTHER, "password": PASSWORD}
            )
            for path in (
                f"/api/imports/{batch['id']}",
                f"/api/imports/{batch['id']}/original",
            ):
                response = other_client.get(path)
                # 别人的资源一律 404，403 会泄露"这个 ID 存在"
                self.assertEqual(404, response.status_code, path)
                self.assertEqual("RESOURCE_NOT_FOUND", response.json()["error"]["code"])
        finally:
            other_client.__exit__(None, None, None)

    def test_original_returns_same_bytes(self) -> None:
        batch = self._pending_batch()
        response = self.client.get(f"/api/imports/{batch['id']}/original")
        self.assertEqual(200, response.status_code)
        self.assertEqual(WECHAT_SAMPLE, response.content)
        disposition = response.headers.get("content-disposition", "")
        self.assertIn("attachment", disposition)
        self.assertIn("filename*=UTF-8''", disposition)

    def test_unparsable_file_fails_with_intelligence_code(self) -> None:
        """不是账单的 CSV：整体失败，但必须给出可判断的 code，不能只报 500。"""
        created = self._upload_ok(data="a,b\n1,2\n".encode("utf-8"), name="junk.csv")
        batch = self._wait_status(created["id"], {"failed", "pending_review"})
        self.assertEqual("failed", batch["status"])
        codes = {issue["code"] for issue in batch["issues"]}
        self.assertIn("UNSUPPORTED_TEMPLATE", codes)
        self.assertEqual([], batch["rows"])

    # ---------------------------------------------------------------- 重试

    def test_retry_rejects_non_failed_batch(self) -> None:
        batch = self._pending_batch()
        response = self.client.post(
            f"/api/imports/{batch['id']}/retry",
            json={"expected_version": batch["version"]},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(409, response.status_code, response.text)
        self.assertEqual("BATCH_STATE_CONFLICT", response.json()["error"]["code"])

    def test_retry_checks_version_then_requeues(self) -> None:
        created = self._upload_ok(data="a,b\n1,2\n".encode("utf-8"), name="junk.csv")
        batch = self._wait_status(created["id"], {"failed"})
        stale = self._retry(batch["id"], batch["version"] + 5)
        self.assertEqual("VERSION_CONFLICT", stale.json()["error"]["code"])
        self.assertEqual(batch["version"], stale.json()["error"]["details"]["current_version"])

        accepted = self._retry(batch["id"], batch["version"])
        self.assertEqual(202, accepted.status_code, accepted.text)
        self.assertEqual(f"/api/imports/{batch['id']}", accepted.headers.get("location"))
        self.assertIn(accepted.json()["status"], {"uploaded", "processing"})
        # 重试后版本必须递增，旧页面的版本号立刻失效
        self.assertGreater(accepted.json()["version"], batch["version"])

        again = self._wait_status(batch["id"], {"failed", "pending_review"})
        self.assertEqual("failed", again["status"])

    def _retry(self, batch_id: str, expected_version: int):
        return self.client.post(
            f"/api/imports/{batch_id}/retry",
            json={"expected_version": expected_version},
            headers={"X-CSRF-Token": self.csrf},
        )

    # ---------------------------------------------------------------- 确认入账

    def test_confirm_creates_transactions_once(self) -> None:
        before = self._txn_count()
        batch = self._pending_batch()
        payload = self._confirm_payload(batch)
        response = self._confirm(batch["id"], payload)
        self.assertEqual(200, response.status_code, response.text)
        result = response.json()
        self.assertEqual(batch["id"], result["batch_id"])
        self.assertEqual(6, result["created_count"])
        self.assertEqual(0, result["duplicate_count"])
        self.assertEqual(0, result["ignored_count"])
        self.assertEqual(6, len(result["transaction_ids"]))
        self.assertEqual(before + 6, self._txn_count())

        completed = self.client.get(f"/api/imports/{batch['id']}").json()
        self.assertEqual("completed", completed["status"])
        self.assertGreater(completed["version"], batch["version"])

        db = app.state.session_factory()
        try:
            user = db.scalar(
                select(models.User).where(models.User.username == self.username)
            )
            row = db.scalar(
                select(models.Transaction).where(
                    models.Transaction.id == result["transaction_ids"][0]
                )
            )
            self.assertEqual(user.id, row.user_id)
            self.assertEqual("confirmed", row.status)
            self.assertEqual("2026-11", row.month_index)
            self.assertEqual("wechat", row.source)
            # 金额与商户只在加密区；表上只留月份/类别/流向这类必要索引列
            payload_json = decrypt_json(
                "test-data-key-not-for-production", row.encrypted_payload
            )
            self.assertEqual(3500, payload_json["amount_fen"])
            self.assertEqual("星巴克咖啡", payload_json["merchant"])
            columns = set(row.__table__.columns.keys())
            self.assertNotIn("amount_fen", columns)
            self.assertNotIn("merchant", columns)
        finally:
            db.close()

    def test_confirm_replay_returns_same_result(self) -> None:
        batch = self._pending_batch()
        payload = self._confirm_payload(batch)
        first = self._confirm(batch["id"], payload)
        self.assertEqual(200, first.status_code)
        after_first = self._txn_count()

        replay = self._confirm(batch["id"], payload)
        self.assertEqual(200, replay.status_code, replay.text)
        self.assertEqual(first.json(), replay.json())
        self.assertEqual(after_first, self._txn_count(), "重放不得重复入账")

    def test_confirm_same_request_id_different_body_conflicts(self) -> None:
        batch = self._pending_batch()
        payload = self._confirm_payload(batch)
        self.assertEqual(200, self._confirm(batch["id"], payload).status_code)

        changed = self._confirm_payload(batch, request_id=payload["request_id"])
        changed["rows"][0]["transaction"]["amount_fen"] = 1
        response = self._confirm(batch["id"], changed)
        self.assertEqual(409, response.status_code, response.text)
        self.assertEqual("IDEMPOTENCY_CONFLICT", response.json()["error"]["code"])

    def test_confirm_completed_batch_with_new_request_conflicts(self) -> None:
        batch = self._pending_batch()
        self.assertEqual(200, self._confirm(batch["id"], self._confirm_payload(batch)).status_code)
        response = self._confirm(batch["id"], self._confirm_payload(batch))
        self.assertEqual(409, response.status_code, response.text)
        self.assertEqual("BATCH_STATE_CONFLICT", response.json()["error"]["code"])

    def test_confirm_version_conflict_returns_current_version(self) -> None:
        batch = self._pending_batch()
        payload = self._confirm_payload(batch, expected_version=batch["version"] + 3)
        response = self._confirm(batch["id"], payload)
        self.assertEqual(409, response.status_code, response.text)
        body = response.json()["error"]
        self.assertEqual("VERSION_CONFLICT", body["code"])
        self.assertEqual(batch["version"], body["details"]["current_version"])

    def test_confirm_unknown_row_is_rejected(self) -> None:
        batch = self._pending_batch()
        payload = self._confirm_payload(batch, limit=1)
        payload["rows"][0]["row_id"] = "row_not_in_this_batch"
        response = self._confirm(batch["id"], payload)
        self.assertEqual(422, response.status_code, response.text)
        body = response.json()["error"]
        self.assertEqual("VALIDATION_ERROR", body["code"])
        self.assertEqual("UNKNOWN_ROW", body["details"]["fields"][0]["code"])

    def test_confirm_partial_selection_counts_ignored(self) -> None:
        batch = self._pending_batch()
        payload = self._confirm_payload(batch, limit=2)
        response = self._confirm(batch["id"], payload)
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual(2, response.json()["created_count"])
        self.assertEqual(4, response.json()["ignored_count"])

    def test_confirm_rejects_time_without_timezone(self) -> None:
        batch = self._pending_batch()
        payload = self._confirm_payload(batch, limit=1)
        payload["rows"][0]["transaction"]["occurred_at"] = "2026-11-01T09:05:12"
        response = self._confirm(batch["id"], payload)
        self.assertEqual(422, response.status_code, response.text)
        codes = {f["code"] for f in response.json()["error"]["details"]["fields"]}
        self.assertIn("TIME_WITHOUT_TIMEZONE", codes)

    def test_confirm_expired_batch_conflicts(self) -> None:
        batch = self._pending_batch()
        db = app.state.session_factory()
        try:
            record = db.get(models.ImportBatch, batch["id"])
            record.expires_at = utcnow() - timedelta(minutes=1)
            db.commit()
        finally:
            db.close()

        response = self._confirm(batch["id"], self._confirm_payload(batch))
        self.assertEqual(409, response.status_code, response.text)
        self.assertEqual("BATCH_STATE_CONFLICT", response.json()["error"]["code"])

    def test_suspected_duplicate_requires_explicit_allow(self) -> None:
        """疑似重复必须用户显式选择，不能静默入账也不能静默丢弃。

        用白盒方式把某行改成 suspected：真实来源是 D 的解析器（同订单部分退款
        这类无法区分事件的情况），后端的行为必须一致。
        """
        batch = self._pending_batch()
        key = "test-data-key-not-for-production"
        db = app.state.session_factory()
        try:
            record = db.get(models.ImportBatch, batch["id"])
            stored = decrypt_json(key, record.encrypted_rows)
            stored["rows"][0]["duplicate_status"] = "suspected"
            record.encrypted_rows = encrypt_json(key, stored)
            record.version += 1
            db.commit()
        finally:
            db.close()

        refreshed = self.client.get(f"/api/imports/{batch['id']}").json()
        payload = self._confirm_payload(refreshed, limit=1)
        denied = self._confirm(batch["id"], payload)
        self.assertEqual(422, denied.status_code, denied.text)
        codes = {f["code"] for f in denied.json()["error"]["details"]["fields"]}
        self.assertIn("SUSPECTED_DUPLICATE_NOT_ALLOWED", codes)

        allowed = self._confirm_payload(refreshed, limit=1, allow_suspected=True)
        accepted = self._confirm(batch["id"], allowed)
        self.assertEqual(200, accepted.status_code, accepted.text)
        self.assertEqual(1, accepted.json()["created_count"])

    def test_reupload_marks_rows_duplicate(self) -> None:
        first = self._pending_batch()
        self.assertEqual(200, self._confirm(first["id"], self._confirm_payload(first)).status_code)
        before = self._txn_count()

        second = self._pending_batch()
        self.assertEqual("pending_review", second["status"], second.get("issues"))
        statuses = [row["duplicate_status"] for row in second["rows"]]
        self.assertEqual(["duplicate"] * 6, statuses, "重传同一份账单必须整批标重复")

        response = self._confirm(second["id"], self._confirm_payload(second, limit=3))
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual(0, response.json()["created_count"])
        self.assertEqual(3, response.json()["duplicate_count"])
        self.assertEqual(before, self._txn_count(), "重复行不得二次入账")


if __name__ == "__main__":
    unittest.main(verbosity=2)
