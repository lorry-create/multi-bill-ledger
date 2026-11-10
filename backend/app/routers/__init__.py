"""路由注册入口。T00 只有 health 与 auth；T01/T02 在此基础上追加，不改已有路径。"""

from . import auth, health

__all__ = ["auth", "health"]
