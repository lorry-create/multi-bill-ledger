"""HTTP 中间件。

对应 docs/11 第 12 行：「所有成功和失败响应带 X-Contract-Version」。
这不是可选装饰——前端靠它判断后端契约版本是否与 SDK 匹配，缺了就是契约违规。
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class ContractVersionMiddleware:
    """给每个 HTTP 响应加 X-Contract-Version。

    用纯 ASGI 实现而不是 BaseHTTPMiddleware：后者会额外包一层 task、
    破坏 StreamingResponse 与后台任务的执行时机，而导出接口（CSV/PDF）
    恰恰是流式响应。

    已知边界：未被异常处理器接住的 500（ServerErrorMiddleware 直接返回）
    拿不到这个头。该场景属于进程级故障，契约保证的是业务响应。
    """

    def __init__(self, app: ASGIApp, version: str) -> None:
        self.app = app
        self.version = version

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_version(message: Message) -> None:
            if message["type"] == "http.response.start":
                # 不覆盖已有值：将来若某个接口要显式声明不同版本，以它为准
                headers = MutableHeaders(scope=message)
                if "x-contract-version" not in headers:
                    headers["X-Contract-Version"] = self.version
            await send(message)

        await self.app(scope, receive, send_with_version)
