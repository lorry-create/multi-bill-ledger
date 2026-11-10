"""统一错误结构。

契约 0.2.0 规定所有非 2xx 响应形如：
    {"error": {"code": "...", "message": "...", "details": {}}}

FastAPI 默认的 422 结构与 Error 不同（{"detail": [...]}），docs/13 要求统一转换
成 error.details.fields。这里是唯一出口，业务代码只抛 ApiError，不手写 JSONResponse。
"""

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .contracts import Error, ErrorDetails, ErrorError, FieldError

logger = logging.getLogger("app.errors")

_KNOWN_STATUS = {item.value for item in HTTPStatus}

_DEFAULT_MESSAGES = {
    400: "请求不合法",
    401: "未登录或会话已失效",
    403: "没有权限或缺少有效的 CSRF 令牌",
    404: "资源不存在",
    409: "资源版本冲突",
    413: "文件过大",
    415: "不支持的文件类型",
    422: "请求内容不合法",
    429: "请求过于频繁",
    500: "服务内部错误",
    503: "服务当前不可用",
}


def build_error(
    code: str,
    message: str,
    details: ErrorDetails | None = None,
) -> dict[str, Any]:
    payload = Error(
        error=ErrorError(code=code, message=message, details=details or ErrorDetails())
    )
    return payload.model_dump(mode="json", exclude_none=True)


class ApiError(Exception):
    """业务错误。code 是稳定机器码，前端不得依赖 message 文本做判断。"""

    def __init__(
        self,
        code: str,
        status_code: int = 400,
        message: str | None = None,
        details: ErrorDetails | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.status_code = status_code
        self.message = message or _DEFAULT_MESSAGES.get(status_code, "请求失败")
        self.details = details or ErrorDetails()
        self.headers = headers
        super().__init__(self.message)

    def to_response(self) -> JSONResponse:
        return JSONResponse(
            status_code=self.status_code,
            content=build_error(self.code, self.message, self.details),
            headers=self.headers,
        )


def _field_path(loc: tuple[Any, ...]) -> str:
    """('body','rows',0,'amount_fen') -> 'rows[0].amount_fen'"""
    parts: list[str] = []
    for item in loc:
        if item in ("body", "query", "path", "header", "cookie"):
            continue
        if isinstance(item, int):
            if parts:
                parts[-1] = f"{parts[-1]}[{item}]"
            else:
                parts.append(f"[{item}]")
        else:
            parts.append(str(item))
    return ".".join(parts) or "request"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return exc.to_response()

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        fields = [
            FieldError(
                field=_field_path(tuple(err.get("loc", ()))),
                row_id=None,
                code=str(err.get("type", "invalid")),
                message=str(err.get("msg", "字段不合法")),
            )
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=build_error(
                "VALIDATION_FAILED", "请求内容不合法", ErrorDetails(fields=fields)
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            401: "UNAUTHENTICATED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            413: "PAYLOAD_TOO_LARGE",
            415: "UNSUPPORTED_MEDIA_TYPE",
        }.get(exc.status_code, "HTTP_ERROR")
        # Starlette 默认 detail 是英文短语（如 "Not Found"）；只有业务自定义了
        # detail 时才用它，否则用中文默认文案，避免前端把英文展示给用户。
        default_phrase = HTTPStatus(exc.status_code).phrase if exc.status_code in _KNOWN_STATUS else ""
        if isinstance(exc.detail, str) and exc.detail and exc.detail != default_phrase:
            message = exc.detail
        else:
            message = _DEFAULT_MESSAGES.get(exc.status_code, "请求失败")
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error(code, message),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # 记录完整栈到服务端日志，但绝不回传给客户端（避免泄露路径、SQL 或密钥）
        logger.exception("未处理异常 %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500, content=build_error("INTERNAL_ERROR", "服务内部错误")
        )
