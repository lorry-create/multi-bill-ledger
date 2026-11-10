"""健康检查。

契约：GET /health -> 200 {"status":"ok"}，依赖不可用时 503 + Error。
容器编排和 11/13 的部署验证都读这个端点，所以它必须真的探测数据库，
不能无条件返回 ok。
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..contracts import Error
from ..deps import get_db
from ..errors import ApiError

router = APIRouter(tags=["health"])


class HealthOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 不给默认值：契约里 status 是 required，给了默认值 OpenAPI 会把它标成可选，
    # 生成出来的客户端类型就会变成 status?: "ok"，与契约不符。
    status: Literal["ok"]


@router.get(
    "/health",
    response_model=HealthOut,
    responses={503: {"model": Error, "description": "依赖不可用"}},
)
def health(db: Session = Depends(get_db)) -> HealthOut:
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise ApiError("DB_UNAVAILABLE", 503, "数据库不可用") from exc
    return HealthOut(status="ok")
