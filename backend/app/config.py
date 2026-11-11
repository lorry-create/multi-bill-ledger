"""运行配置。

设计口径（对应 .env.example 与本文件顶部的变量表）：

- 所有配置只从环境变量读取，不写默认密钥进代码。
- 开发环境（APP_ENV != production）允许自动生成开发密钥，但必须持久化到
  local-data/dev_secrets.json（.gitignore 已排除），否则进程一重启就解不开
  自己加密过的数据。
- 生产环境必须显式提供 SESSION_SECRET 与 DATA_ENCRYPTION_KEY，缺失时直接
  启动失败，不允许"悄悄用默认值"。
"""

from __future__ import annotations

import json
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
LOCAL_DATA_DIR = BACKEND_DIR / "local-data"
DEV_SECRETS_FILE = LOCAL_DATA_DIR / "dev_secrets.json"

_TRUE = {"1", "true", "yes", "on"}


class ConfigError(RuntimeError):
    """配置缺失或不合法。启动阶段抛出，不带任何密钥内容。"""


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() in _TRUE


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} 必须是整数，实际为 {raw!r}") from exc


def _dev_secrets() -> dict[str, str]:
    """读取或生成开发期密钥，落盘到 local-data/dev_secrets.json。"""
    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if DEV_SECRETS_FILE.exists():
        try:
            data = json.loads(DEV_SECRETS_FILE.read_text(encoding="utf-8"))
            if data.get("session_secret") and data.get("data_encryption_key"):
                return data
        except (OSError, ValueError):
            pass  # 文件损坏则重新生成，代价只是旧的开发密文失效
    data = {
        "session_secret": secrets.token_urlsafe(48),
        "data_encryption_key": secrets.token_hex(32),
        "_note": "仅本机开发使用，已被 .gitignore 排除；生产环境必须用环境变量提供。",
    }
    DEV_SECRETS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    try:
        os.chmod(DEV_SECRETS_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # Windows 上 chmod 语义有限，失败不阻塞启动
    return data


def _sqlite_url() -> str:
    path = (LOCAL_DATA_DIR / "app.db").as_posix()
    return f"sqlite+pysqlite:///{path}"


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: str
    session_secret: str
    data_encryption_key: str
    session_ttl_hours: int
    cookie_secure: bool
    login_max_failures: int
    login_lock_seconds: int
    allow_test_doubles: bool
    cors_origins: tuple[str, ...]
    intelligence_provider: str

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


def load_settings() -> Settings:
    app_env = _env("APP_ENV", "development").lower() or "development"

    database_url = _env("DATABASE_URL")
    if not database_url:
        database_url = _sqlite_url()
        LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)

    session_secret = _env("SESSION_SECRET")
    data_encryption_key = _env("DATA_ENCRYPTION_KEY")

    if not session_secret or not data_encryption_key:
        if app_env == "production":
            missing = [
                name
                for name, value in (
                    ("SESSION_SECRET", session_secret),
                    ("DATA_ENCRYPTION_KEY", data_encryption_key),
                )
                if not value
            ]
            raise ConfigError(
                "生产环境缺少必需配置：" + ", ".join(missing) + "（不允许使用自动生成的开发密钥）"
            )
        dev = _dev_secrets()
        session_secret = session_secret or dev["session_secret"]
        data_encryption_key = data_encryption_key or dev["data_encryption_key"]

    raw_origins = _env("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    cors_origins = tuple(item.strip() for item in raw_origins.split(",") if item.strip())

    return Settings(
        app_env=app_env,
        database_url=database_url,
        session_secret=session_secret,
        data_encryption_key=data_encryption_key,
        session_ttl_hours=_env_int("SESSION_TTL_HOURS", 12),
        cookie_secure=_env_bool("COOKIE_SECURE", app_env == "production"),
        login_max_failures=_env_int("LOGIN_MAX_FAILURES", 5),
        login_lock_seconds=_env_int("LOGIN_LOCK_SECONDS", 60),
        allow_test_doubles=_env_bool("ALLOW_TEST_DOUBLES", False),
        cors_origins=cors_origins,
        # 默认本地 OCR + 规则分类；自定义实现按 包.模块:类名 填入。不自动降级，
        # 否则分类来源会撒谎（见 app/intelligence/factory.py 顶部说明）
        intelligence_provider=_env("INTELLIGENCE_PROVIDER", "local-rapidocr"),
    )
