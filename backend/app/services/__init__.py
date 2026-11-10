"""业务服务层：跨接口复用的计算与事务。

与 routers 的分工（docs/13「HTTP 处理层」）：routers 只做认证、CSRF、请求校验、
资源归属和 HTTP 状态；业务口径与事务在这里；routers 不许自己另算一份。
"""

from __future__ import annotations

from .reporting import build_monthly_report, compute_totals, month_days

__all__ = ["build_monthly_report", "compute_totals", "month_days"]
