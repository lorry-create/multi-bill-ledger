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


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} 必须是数字，实际为 {raw!r}") from exc


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
    deepseek_base_url: str
    deepseek_api_key: str
    deepseek_model: str
    ocr_provider: str
    # 导入中心（T02）：限额与批次时限都来自 docs/02、docs/11、docs/13 的明文规定，
    # 不写成散布在路由里的魔法数字，测试要靠环境变量调小才跑得动
    upload_max_file_bytes: int
    upload_max_image_bytes: int
    batch_deadline_seconds: int
    batch_draft_ttl_hours: int
    import_worker_enabled: bool
    import_worker_poll_seconds: float
    # 导出（T08/T09）：CSV 行数上限防止一次解密几十万条把内存打满；
    # PDF 字体路径留空表示按内置候选列表自动搜索（见 app/services/exporting.py）
    export_max_rows: int
    pdf_font_path: str

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


def _load_dotenv_if_local() -> None:
    """开发期自动加载 REPO_ROOT/.env 或 BACKEND_DIR/.env，不覆盖已显式设置的环境变量。"""
    if (os.environ.get("APP_ENV") or "").strip().lower() == "test":
        return
    for candidate in (BACKEND_DIR / ".env", REPO_ROOT / ".env"):
        if not candidate.is_file():
            continue
        for raw_line in candidate.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, val)


def load_settings() -> Settings:
    _load_dotenv_if_local()
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
        # 默认纯规则实现；D 的实现按 包.模块:类名 填入。故意不支持"自动降级"，
        # 否则分类来源会撒谎（见 app/intelligence/factory.py 顶部说明）
        intelligence_provider=_env("INTELLIGENCE_PROVIDER", "fallback-rules"),
        deepseek_base_url=_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_api_key=_env("DEEPSEEK_API_KEY", ""),
        deepseek_model=_env("DEEPSEEK_MODEL", "deepseek-chat"),
        ocr_provider=_env("OCR_PROVIDER", "rapidocr"),
        # 契约 docs/11 createImport：文件 10MiB、图片 5MiB
        upload_max_file_bytes=_env_int("UPLOAD_MAX_FILE_BYTES", 10 * 1024 * 1024),
        upload_max_image_bytes=_env_int("UPLOAD_MAX_IMAGE_BYTES", 5 * 1024 * 1024),
        # docs/13：整体批次期限 300 秒，超时转 failed，不允许永久 processing
        batch_deadline_seconds=_env_int("BATCH_DEADLINE_SECONDS", 300),
        batch_draft_ttl_hours=_env_int("BATCH_DRAFT_TTL_HOURS", 24),
        import_worker_enabled=_env_bool("IMPORT_WORKER_ENABLED", True),
        import_worker_poll_seconds=_env_float("IMPORT_WORKER_POLL_SECONDS", 0.5),
        # 单次导出 5 万行封顶：个人账单一月几千行量级，这个上限只用来防异常调用
        export_max_rows=_env_int("EXPORT_MAX_ROWS", 50000),
        # 留空则由 exporting._find_cjk_font() 按候选列表找；容器里显式指到
        # /usr/share/fonts/truetype/wqy/wqy-zenhei.ttc（TrueType 轮廓，reportlab 能嵌入）
        pdf_font_path=_env("PDF_FONT_PATH", ""),
    )
