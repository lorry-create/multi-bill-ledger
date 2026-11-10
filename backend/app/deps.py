"""请求级依赖：数据库会话、登录态、CSRF 校验。"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .contracts import ErrorDetails
from .db import as_utc, utcnow
from .errors import ApiError
from .security import constant_time_equals, token_fingerprint

SESSION_COOKIE = "bill_session"
CSRF_HEADER = "X-CSRF-Token"

# 会话最后活跃时间每隔这么久才落库一次，避免每个请求都写一行
_TOUCH_INTERVAL_SECONDS = 300


def get_db(request: Request) -> Iterator[Session]:
    factory = request.app.state.session_factory
    db: Session = factory()
    try:
        yield db
    finally:
        db.close()


@dataclass(frozen=True)
class AuthContext:
    user: models.User
    session: models.UserSession


def _unauthenticated(code: str, message: str) -> ApiError:
    return ApiError(code, 401, message)


def require_session(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    """校验会话 Cookie。GET 接口用它，写接口用 require_csrf。"""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise _unauthenticated("AUTH_REQUIRED", "未登录或会话已失效")

    row = db.scalar(
        select(models.UserSession).where(
            models.UserSession.token_hash == token_fingerprint(token)
        )
    )
    if row is None:
        raise _unauthenticated("AUTH_REQUIRED", "未登录或会话已失效")

    now = utcnow()
    expires_at = as_utc(row.expires_at)
    if expires_at is None or expires_at <= now:
        db.delete(row)
        db.commit()
        raise _unauthenticated("AUTH_REQUIRED", "会话已过期，请重新登录")

    user = db.get(models.User, row.user_id)
    if user is None or not user.is_active:
        db.delete(row)
        db.commit()
        raise _unauthenticated("AUTH_REQUIRED", "账号不可用")

    last_seen = as_utc(row.last_seen_at)
    if last_seen is None or (now - last_seen).total_seconds() >= _TOUCH_INTERVAL_SECONDS:
        row.last_seen_at = now
        db.commit()

    return AuthContext(user=user, session=row)


def require_csrf(
    request: Request, auth: AuthContext = Depends(require_session)
) -> AuthContext:
    """写请求必须同时带会话 Cookie 与 X-CSRF-Token 头（同步令牌方案）。"""
    provided = request.headers.get(CSRF_HEADER) or ""
    if not provided or not constant_time_equals(provided, auth.session.csrf_token):
        raise ApiError(
            "CSRF_INVALID",
            403,
            "缺少或无效的 CSRF 令牌",
            ErrorDetails(),
        )
    return auth
