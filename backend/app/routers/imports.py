"""导入中心路由：上传、读批次、读原文件、重试、确认入账。

契约（contracts/openapi.json 0.2.0）：
    POST /api/imports                  -> 202 Batch | 401 | 403 | 413 | 415 | 422
    GET  /api/imports/{id}             -> 200 Batch | 401 | 404
    GET  /api/imports/{id}/original    -> 200 二进制  | 401 | 404 | 503
    POST /api/imports/{id}/retry       -> 202 Batch | 401 | 403 | 404 | 409
    POST /api/imports/{id}/confirm     -> 200 ConfirmResult | 401 | 403 | 404 | 409 | 422

本文件只做 HTTP 适配：读表单、读写响应头、把 service 的异常交给统一错误处理。
状态机、幂等、去重、事务全在 app/services/imports.py，别在这里加业务判断。
"""

from __future__ import annotations

import os
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from sqlalchemy.orm import Session

from ..contracts import (
    Batch,
    ConfirmInput,
    ConfirmResult,
    Error,
    ErrorDetails,
    IngestionMethod,
    RetryInput,
    Source,
)
from ..crypto import CryptoError, decrypt_bytes
from ..deps import AuthContext, get_db, require_csrf, require_session
from ..errors import ApiError
from ..services import imports

router = APIRouter(prefix="/api/imports", tags=["imports"])

# 非 2xx 一律是统一 Error 结构；显式声明，避免 FastAPI 把 422 文档写成 {"detail": []}
_ERR = {"model": Error, "description": "统一错误结构"}

_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")


@router.post(
    "",
    status_code=202,
    response_model=Batch,
    responses={401: _ERR, 403: _ERR, 413: _ERR, 415: _ERR, 422: _ERR},
)
def create_import(
    request: Request,
    response: Response,
    source: Source = Form(...),
    ingestion_method: IngestionMethod = Form(...),
    file: UploadFile = File(...),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Batch:
    """只创建批次并返回 202，绝不在请求内解析。

    解析放请求里会有两个坏结果：大文件把响应拖到超时（用户以为失败，其实成功了），
    以及进程重启后批次卡死。这里返回 `Location` + `Retry-After`，前端按契约轮询。
    """
    settings = request.app.state.settings

    # 先定类型再读内容：上限取决于类型（文件 10MiB / 图片 5MiB）
    target = imports.resolve_target(ingestion_method, file.filename, settings)
    data = imports.read_limited(file.file, target)
    imports.check_content(target, data)

    batch = imports.create_batch(
        db,
        user_id=auth.user.id,
        source=source,
        method=ingestion_method,
        target=target,
        data=data,
        settings=settings,
    )

    response.headers["Location"] = f"/api/imports/{batch.id}"
    # 契约规定这个头；前端首轮轮询按它 1 秒后再来
    response.headers["Retry-After"] = "1"
    return imports.to_contract(batch, settings.data_encryption_key)


@router.get("/{id}", response_model=Batch, responses={401: _ERR, 404: _ERR})
def get_import(
    id: str,
    request: Request,
    auth: AuthContext = Depends(require_session),
    db: Session = Depends(get_db),
) -> Batch:
    batch = imports.load_owned(db, auth.user.id, id)
    return imports.to_contract(batch, request.app.state.settings.data_encryption_key)


@router.get(
    "/{id}/original",
    response_class=Response,
    responses={
        200: {
            "description": "原文件或原图",
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        },
        401: _ERR,
        404: _ERR,
        503: _ERR,
    },
)
def get_import_original(
    id: str,
    request: Request,
    auth: AuthContext = Depends(require_session),
    db: Session = Depends(get_db),
) -> Response:
    """鉴权解密后回传原件，供用户在确认页对照。

    原件不进任何静态目录、不给公开 URL——账单里有全部消费记录，一个可猜的
    路径就等于数据泄露。解密失败返回 503 而不是 500：这是密钥/存储层面的
    问题，不是请求有问题，前端文案也不一样。
    """
    settings = request.app.state.settings
    batch = imports.load_owned(db, auth.user.id, id)

    if not batch.encrypted_original:
        raise ApiError("RESOURCE_NOT_FOUND", 404, "资源不存在")
    try:
        data = decrypt_bytes(settings.data_encryption_key, batch.encrypted_original)
    except CryptoError:
        raise ApiError(
            "SERVICE_UNAVAILABLE", 503, "原文件暂时无法读取，请重新上传该账单"
        ) from None

    meta = imports.file_meta(batch, settings.data_encryption_key)
    name = meta["name"]
    inline = os.path.splitext(name)[1].lower() in _IMAGE_SUFFIXES
    headers = {
        "Content-Disposition": _content_disposition(name, inline=inline),
        # 账单原件不能进浏览器缓存、不能被当作别的类型解释
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    return Response(content=data, media_type=meta["media_type"], headers=headers)


@router.post(
    "/{id}/retry",
    status_code=202,
    response_model=Batch,
    responses={401: _ERR, 403: _ERR, 404: _ERR, 409: _ERR},
)
def retry_import(
    id: str,
    payload: RetryInput,
    request: Request,
    response: Response,
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Batch:
    """只重跑失败批次，且版本必须相符。

    已完成批次不允许重跑：确认入账是不可逆的，重跑只会产生一批"看起来新"的
    重复草稿，用户点了确认才发现全被去重跳过。
    """
    settings = request.app.state.settings
    batch = imports.load_owned(db, auth.user.id, id)

    imports.ensure_pending_state(batch)
    if payload.expected_version != batch.version:
        raise ApiError(
            "VERSION_CONFLICT",
            409,
            "批次已被修改，请刷新后重试",
            details=ErrorDetails(current_version=batch.version),
        )

    imports.reset_for_retry(db, batch)
    response.headers["Location"] = f"/api/imports/{batch.id}"
    response.headers["Retry-After"] = "1"
    return imports.to_contract(batch, settings.data_encryption_key)


@router.post(
    "/{id}/confirm",
    response_model=ConfirmResult,
    responses={401: _ERR, 403: _ERR, 404: _ERR, 409: _ERR, 422: _ERR},
)
def confirm_import(
    id: str,
    payload: ConfirmInput,
    request: Request,
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> ConfirmResult:
    settings = request.app.state.settings
    batch = imports.load_owned(db, auth.user.id, id)
    return imports.confirm_batch(db, batch, payload, settings)


# ---------------------------------------------------------------- 内部工具


def _content_disposition(name: str, *, inline: bool) -> str:
    """中文文件名要给 RFC 5987 的 `filename*`，否则浏览器存成乱码。

    `filename=` 里的 ASCII 兜底串把非 ASCII 换成下划线，老浏览器也不会炸。
    """
    ascii_name = "".join(ch if 32 <= ord(ch) < 127 and ch not in '"\\' else "_" for ch in name)
    kind = "inline" if inline else "attachment"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name, safe='')}"
