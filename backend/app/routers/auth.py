"""认证路由：登录、当前会话、登出。

契约（contracts/openapi.json 0.2.0）：
    POST /api/auth/login   -> 200 Session | 401 | 403 | 422 | 429
    GET  /api/auth/me      -> 200 Session | 401
    POST /api/auth/logout  -> 204 | 401 | 403（需 CSRF）
"""

from __future__ import annotations

import math
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models
from ..contracts import Error, ErrorDetails, LoginInput
from ..contracts import Session as SessionModel
from ..contracts import User as UserModel
from ..db import as_utc, utcnow
from ..deps import SESSION_COOKIE, AuthContext, get_db, require_csrf, require_session
from ..errors import ApiError
from ..security import hash_password, new_token, token_fingerprint, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 非 2xx 一律走统一 Error 结构。这里显式声明，否则 FastAPI 会把 422 文档写成
# 它自己的 {"detail": [...]}，生成出来的客户端类型与契约（error.details.fields）不符。
_ERR = {"model": Error, "description": "统一错误结构"}

# 用户不存在时也做一次等价的慢哈希，避免通过响应时间判断账号是否存在
_DUMMY_HASH = hash_password("timing-equalizer-not-a-real-password")


def _session_payload(user: models.User, csrf_token: str) -> SessionModel:
    return SessionModel(
        user=UserModel(id=user.id, username=user.username), csrf_token=csrf_token
    )


def _locked(wait_seconds: int) -> ApiError:
    return ApiError(
        "LOGIN_LOCKED",
        429,
        "登录失败次数过多，请稍后再试",
        ErrorDetails(retry_after_seconds=max(1, wait_seconds)),
        headers={"Retry-After": str(max(1, wait_seconds))},
    )


@router.post(
    "/login",
    response_model=SessionModel,
    responses={401: _ERR, 403: _ERR, 422: _ERR, 429: _ERR},
)
def login(
    payload: LoginInput,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> SessionModel:
    settings = request.app.state.settings
    now = utcnow()

    user = db.scalar(select(models.User).where(models.User.username == payload.username))

    if user is None:
        verify_password(payload.password, _DUMMY_HASH)
        raise ApiError("AUTH_INVALID", 401, "账号或密码不正确")

    locked_until = as_utc(user.locked_until)
    if locked_until is not None and locked_until > now:
        raise _locked(math.ceil((locked_until - now).total_seconds()))

    if not user.is_active:
        raise ApiError("ACCOUNT_DISABLED", 401, "账号不可用")

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.login_max_failures:
            user.failed_login_count = 0
            user.locked_until = now + timedelta(seconds=settings.login_lock_seconds)
            db.commit()
            raise _locked(settings.login_lock_seconds)
        db.commit()
        raise ApiError("AUTH_INVALID", 401, "账号或密码不正确")

    # 成功：清空失败计数，顺手清掉该用户已过期的会话（避免表无限增长）
    user.failed_login_count = 0
    user.locked_until = None
    db.execute(
        delete(models.UserSession).where(
            models.UserSession.user_id == user.id,
            models.UserSession.expires_at <= now,
        )
    )

    token = new_token()
    csrf_token = new_token()
    db.add(
        models.UserSession(
            id=str(uuid.uuid4()),
            user_id=user.id,
            token_hash=token_fingerprint(token),
            csrf_token=csrf_token,
            expires_at=now + timedelta(hours=settings.session_ttl_hours),
            last_seen_at=now,
            user_agent=(request.headers.get("user-agent") or "")[:255] or None,
            client_ip=(request.client.host if request.client else None),
        )
    )
    db.commit()

    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return _session_payload(user, csrf_token)


@router.get("/me", response_model=SessionModel, responses={401: _ERR})
def get_session(auth: AuthContext = Depends(require_session)) -> SessionModel:
    return _session_payload(auth.user, auth.session.csrf_token)


@router.post("/logout", status_code=204, responses={401: _ERR, 403: _ERR})
def logout(
    response: Response,
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Response:
    db.delete(auth.session)
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = 204
    return response
