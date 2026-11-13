"""敏感字段加密与去重摘要。

对应 docs/13：金额、精确时间、交易号、商户、说明、分类依据进入 encrypted_payload；
去重使用「带独立密钥的 HMAC 摘要」建唯一索引，原号加密，不建明文商户库。

实现说明：
- AES-256-GCM，每条记录独立 12 字节随机 nonce，密文自带完整性校验。
- 明文为 JSON（UTF-8），密文格式 `v1.<base64url(nonce||ciphertext)>`，版本前缀
  便于以后换算法时平滑迁移。
- 去重摘要用 HMAC-SHA256，key 由 data_encryption_key 派生（不同用途不同 key，
  不复用同一把原始密钥）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_VERSION = "v1"
_NONCE_BYTES = 12


class CryptoError(RuntimeError):
    """密文损坏或密钥不匹配。消息里不包含密文与明文内容。"""


def _derive(master: str, purpose: bytes) -> bytes:
    return hmac.new(master.encode("utf-8"), purpose, hashlib.sha256).digest()


def _encode(master: str, purpose: bytes, raw: bytes) -> str:
    nonce = os.urandom(_NONCE_BYTES)
    sealed = AESGCM(_derive(master, purpose)).encrypt(nonce, raw, None)
    return f"{_VERSION}.{base64.urlsafe_b64encode(nonce + sealed).decode('ascii')}"


def _decode(master: str, purpose: bytes, token: str) -> bytes:
    if not token.startswith(_VERSION + "."):
        raise CryptoError("不支持的密文版本")
    try:
        blob = base64.urlsafe_b64decode(token[len(_VERSION) + 1 :].encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise CryptoError("密文编码非法") from exc
    if len(blob) <= _NONCE_BYTES:
        raise CryptoError("密文过短")
    nonce, sealed = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    try:
        return AESGCM(_derive(master, purpose)).decrypt(nonce, sealed, None)
    except Exception as exc:  # cryptography 抛 InvalidTag 等，统一收口
        raise CryptoError("密文校验失败") from exc


def encrypt_json(master: str, payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _encode(master, b"payload-json", raw.encode("utf-8"))


def decrypt_json(master: str, token: str) -> dict[str, Any]:
    data = _decode(master, b"payload-json", token)
    try:
        value = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise CryptoError("密文内容不是合法 JSON") from exc
    if not isinstance(value, dict):
        raise CryptoError("密文内容不是对象")
    return value


def encrypt_bytes(master: str, raw: bytes) -> str:
    return _encode(master, b"blob", raw)


def decrypt_bytes(master: str, token: str) -> bytes:
    return _decode(master, b"blob", token)


def dedupe_digest(master: str, *parts: str) -> str:
    """去重摘要：同一用户 + 平台 + 事件性质 + 源事件号的稳定指纹。

    注意（docs/13）：同一订单的多次部分退款不能用订单号一刀切。调用方必须把
    「事件性质」放进 parts，待真实样本验证后由 H 与 D 约定更精确的字段来源。
    """
    key = _derive(master, b"dedupe-digest")
    joined = "\x1f".join(parts).encode("utf-8")
    return hmac.new(key, joined, hashlib.sha256).hexdigest()


def file_digest(master: str, data: bytes) -> str:
    """原始上传文件字节摘要：仅用于同用户重复上传检测，不可逆推出原文件。"""
    key = _derive(master, b"file-digest")
    return hmac.new(key, data, hashlib.sha256).hexdigest()
