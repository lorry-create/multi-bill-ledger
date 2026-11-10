"""密码哈希、会话令牌与 CSRF 令牌。

密码：标准库 hashlib.scrypt（内存硬化），格式
`scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>`，参数随记录存储，以后调参可平滑
验证旧密码。选 scrypt 而不是 bcrypt 是为了不引入额外二进制依赖（cryptography
已依赖，但 bcrypt 需要单独编译轮）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 32
_PREFIX = "scrypt"


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("密码不能为空")
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_DKLEN,
    )
    return f"{_PREFIX}${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(derived)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        prefix, n, r, p, salt_b64, hash_b64 = encoded.split("$")
        if prefix != _PREFIX:
            return False
        derived = hashlib.scrypt(
            (password or "").encode("utf-8"),
            salt=_unb64(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(_unb64(hash_b64)),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived, _unb64(hash_b64))


def new_token() -> str:
    """会话令牌 / CSRF 令牌，256 位熵。"""
    return secrets.token_urlsafe(32)


def token_fingerprint(token: str) -> str:
    """入库只存摘要：数据库泄露也拿不到可用的会话令牌。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest((left or "").encode("utf-8"), (right or "").encode("utf-8"))
