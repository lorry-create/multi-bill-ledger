"""FastAPI 应用入口。

启动：
    cd backend
    python -m app.migrate          # 建表
    python -m app.seed_demo ...    # 可选：导入合成演示数据
    python -m uvicorn app.main:app --reload --port 8000

已实现接口：/health、/api/auth/*、/api/imports/*（T02 导入中心 5 个）。
其余接口由 T05/T08 按契约补齐。后端自己导出的 /openapi.json 反映"已实现部分"，
不是权威契约；权威仍是 contracts/openapi.json，两边不一致时必须先改文档再改代码。
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
from .intelligence.factory import build_intelligence
from .middleware import ContractVersionMiddleware
from .routers import auth, health
from .routers import imports as imports_api
from .services.worker import ImportWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("app.main")

_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def strip_unreachable_422(schema: dict) -> dict:
    """摘掉"不可能发生"的 422 声明。

    FastAPI 只要看到路径参数就无条件往 OpenAPI 里加 422（Pydantic 校验失败）。
    但 `GET /api/imports/{id}` 这种端点唯一的入参是**纯字符串**路径段——它
    永远不会校验失败，422 这个分支在服务端不存在。契约（contracts/openapi.json）
    也没有声明它，多出来会让生成的客户端多一个永不触发的错误分支，
    tools/check_implemented_contract.py 也会判不一致。

    规则收紧到"无请求体、无 query/header/cookie 参数、路径参数全为裸 string"
    才摘，带请求体或有约束的端点（createImport / confirmImport）的 422 保留。
    """
    for methods in schema.get("paths", {}).values():
        for method, operation in methods.items():
            if method not in _METHODS or "requestBody" in operation:
                continue
            params = operation.get("parameters", [])
            if any(param.get("in") in {"query", "header", "cookie"} for param in params):
                continue
            path_params = [param for param in params if param.get("in") == "path"]
            plain_strings = all(
                param.get("schema", {}).get("type") == "string"
                and set(param.get("schema", {})) <= {"type", "title"}
                for param in path_params
            )
            if plain_strings:
                operation.get("responses", {}).pop("422", None)
    return schema


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info(
            "启动 env=%s db=%s cookie_secure=%s",
            settings.app_env,
            "sqlite" if settings.is_sqlite else "postgresql",
            settings.cookie_secure,
        )
        worker: ImportWorker | None = None
        if settings.import_worker_enabled:
            # 取不到实现就在这里失败（factory 不自动降级），别等到用户上传完才发现
            provider = build_intelligence(settings.intelligence_provider)
            worker = ImportWorker(session_factory, provider, settings)
            worker.start()
        app.state.import_worker = worker
        try:
            yield
        finally:
            if worker is not None:
                worker.stop()
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
    app.include_router(imports_api.router)

    # 后端的 /openapi.json 是"已实现部分"的自描述，得和权威契约对得上
    _original_openapi = app.openapi

    def _openapi() -> dict:
        return strip_unreachable_422(_original_openapi())

    app.openapi = _openapi

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
