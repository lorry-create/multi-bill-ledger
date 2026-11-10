"""FastAPI 应用入口。

启动：
    cd backend
    python -m app.migrate          # 建表
    python -m app.seed_demo ...    # 可选：导入合成演示数据
    python -m uvicorn app.main:app --reload --port 8000

T00 只暴露 /health 与 /api/auth/*，其余 13 个接口由 T01/T02 按契约逐个补齐。
后端自己导出的 /openapi.json 反映"已实现部分"，不是权威契约；权威仍是
contracts/openapi.json，两边不一致时必须先改文档再改代码（docs/13 末尾）。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, load_settings
from .contracts import CONTRACT_VERSION
from .db import build_engine, build_session_factory
from .errors import register_error_handlers
from .middleware import ContractVersionMiddleware
from .routers import auth, health

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("app.main")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        logger.info(
            "启动 env=%s db=%s cookie_secure=%s",
            settings.app_env,
            "sqlite" if settings.is_sqlite else "postgresql",
            settings.cookie_secure,
        )
        yield
        engine.dispose()

    app = FastAPI(
        title="multi-bill-ledger",
        version=CONTRACT_VERSION,
        description="多平台个人账单智能整理与月度分析系统（赛题 B）",
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory

    register_error_handlers(app)
    app.add_middleware(ContractVersionMiddleware, version=CONTRACT_VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
        # 不给 expose，浏览器里的 JS 读不到这个响应头
        expose_headers=["X-Contract-Version", "Location", "Retry-After"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
