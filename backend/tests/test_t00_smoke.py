"""T00 冒烟测试：健康检查、登录、会话、CSRF、错误结构、登录限流。

设计要点：
- 用标准库 unittest，不引入 pytest，队友 clone 下来就能跑。
- 全程使用临时 SQLite 库，不碰 backend/local-data/app.db，也不占用 8000 端口。
- 断言的是**契约**（contracts/openapi.json 0.2.0）规定的状态码与错误结构，
  不是"当前实现碰巧返回什么"，因此这些用例在 T01/T02 继续有效。

运行（在 backend/ 目录）：
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from pathlib import Path

# 必须在导入 app.main 之前设置：模块导入时会 create_app()，否则会写真实开发库
_TMP_DIR = tempfile.mkdtemp(prefix="mbl_t00_test_")
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{Path(_TMP_DIR, 'test.db').as_posix()}"
os.environ["SESSION_SECRET"] = "test-session-secret-not-for-production"
os.environ["DATA_ENCRYPTION_KEY"] = "test-data-key-not-for-production"
os.environ["COOKIE_SECURE"] = "0"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import models  # noqa: E402
from app.db import Base  # noqa: E402
from app.main import app  # noqa: E402
from app.security import hash_password  # noqa: E402

PASSWORD = "demo-pass-2026"
LOCK_PASSWORD = "lock-pass-2026"


def _make_user(username: str, password: str) -> None:
    factory = app.state.session_factory
    db = factory()
    try:
        existing = db.scalar(select(models.User).where(models.User.username == username))
        if existing is None:
            db.add(
                models.User(
                    id=str(uuid.uuid4()),
                    username=username,
                    password_hash=hash_password(password),
                    is_active=True,
                )
            )
            db.commit()
    finally:
        db.close()


class T00SmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Base.metadata.create_all(app.state.engine)
        _make_user("demo_a", PASSWORD)
        _make_user("demo_lock", LOCK_PASSWORD)

    def setUp(self) -> None:
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()

    # ---------- 健康检查 ----------
    def test_health_ok(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "ok"}, response.json())

    # ---------- 认证前 ----------
    def test_me_requires_session(self) -> None:
        response = self.client.get("/api/auth/me")
        self.assertEqual(401, response.status_code)
        body = response.json()
        self.assertEqual({"error"}, set(body))
        self.assertEqual({"code", "message", "details"}, set(body["error"]))
        self.assertEqual("UNAUTHENTICATED", body["error"]["code"])

    # ---------- 登录 ----------
    def test_login_wrong_password(self) -> None:
        response = self.client.post(
            "/api/auth/login", json={"username": "demo_a", "password": "wrong"}
        )
        self.assertEqual(401, response.status_code)
        self.assertEqual("INVALID_CREDENTIALS", response.json()["error"]["code"])

    def test_login_unknown_user_same_code(self) -> None:
        """不泄露账号是否存在：不存在的账号与密码错误返回同一 code。"""
        response = self.client.post(
            "/api/auth/login", json={"username": "ghost-user", "password": "x"}
        )
        self.assertEqual(401, response.status_code)
        self.assertEqual("INVALID_CREDENTIALS", response.json()["error"]["code"])

    def test_login_validation_uses_contract_error_shape(self) -> None:
        response = self.client.post("/api/auth/login", json={"username": "", "password": ""})
        self.assertEqual(422, response.status_code)
        body = response.json()
        self.assertEqual("VALIDATION_FAILED", body["error"]["code"])
        fields = body["error"]["details"]["fields"]
        self.assertGreaterEqual(len(fields), 1)
        self.assertIn("username", {item["field"] for item in fields})

    def test_login_success_returns_session_and_cookie(self) -> None:
        response = self.client.post(
            "/api/auth/login", json={"username": "demo_a", "password": PASSWORD}
        )
        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual({"user", "csrf_token"}, set(body))
        self.assertEqual("demo_a", body["user"]["username"])
        self.assertGreaterEqual(len(body["csrf_token"]), 32)
        self.assertIn("bill_session", response.cookies)

        cookie_header = response.headers.get("set-cookie", "").lower()
        self.assertIn("httponly", cookie_header)
        self.assertIn("samesite=lax", cookie_header)

        # 会话可读回，且 csrf_token 稳定
        me = self.client.get("/api/auth/me")
        self.assertEqual(200, me.status_code)
        self.assertEqual(body["csrf_token"], me.json()["csrf_token"])
        self.assertEqual(body["user"]["id"], me.json()["user"]["id"])

    # ---------- CSRF ----------
    def test_write_requires_csrf(self) -> None:
        login = self.client.post(
            "/api/auth/login", json={"username": "demo_a", "password": PASSWORD}
        )
        csrf = login.json()["csrf_token"]

        missing = self.client.post("/api/auth/logout")
        self.assertEqual(403, missing.status_code)
        self.assertEqual("CSRF_TOKEN_INVALID", missing.json()["error"]["code"])

        wrong = self.client.post("/api/auth/logout", headers={"X-CSRF-Token": "nope"})
        self.assertEqual(403, wrong.status_code)

        ok = self.client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
        self.assertEqual(204, ok.status_code)

        # 登出后会话必须立即失效
        self.assertEqual(401, self.client.get("/api/auth/me").status_code)

    # ---------- 统一 404 ----------
    def test_unknown_path_uses_error_shape(self) -> None:
        response = self.client.get("/api/definitely-not-a-route")
        self.assertEqual(404, response.status_code)
        self.assertIn("error", response.json())

    # ---------- 登录限流 ----------
    def test_login_lockout_after_repeated_failures(self) -> None:
        codes = []
        last = None
        for _ in range(5):
            last = self.client.post(
                "/api/auth/login", json={"username": "demo_lock", "password": "bad"}
            )
            codes.append(last.status_code)
        self.assertEqual(429, codes[-1], f"连续失败状态码序列：{codes}")
        body = last.json()["error"]
        self.assertEqual("LOGIN_LOCKED", body["code"])
        self.assertGreaterEqual(body["details"]["retry_after_seconds"], 1)
        self.assertIsNotNone(last.headers.get("retry-after"))

        # 锁定期间即使密码正确也拒绝
        still_locked = self.client.post(
            "/api/auth/login", json={"username": "demo_lock", "password": LOCK_PASSWORD}
        )
        self.assertEqual(429, still_locked.status_code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
