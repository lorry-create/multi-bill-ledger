"""个人分类规则。

闭环第五环的两个接口：列出本人规则、改类别或停用/启用。
`patchRule` 是 docs/08 A07 的最后一步——没有它，用户能"记住商户"却永远停不掉，
反馈闭环就是假闭合。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..contracts import ClassificationRule, Error, RuleList, RulePatch
from ..deps import AuthContext, get_db, require_csrf, require_session
from ..services import rules as rule_service

router = APIRouter(prefix="/api/classification-rules", tags=["个人规则页"])

_ERR = {"model": Error, "description": "统一错误结构"}


@router.get("", response_model=RuleList, responses={401: _ERR})
def list_rules(
    request: Request,
    auth: AuthContext = Depends(require_session),
    db: Session = Depends(get_db),
) -> RuleList:
    return rule_service.list_rules(
        db, auth.user.id, request.app.state.settings.data_encryption_key
    )


@router.patch(
    "/{id}",
    response_model=ClassificationRule,
    responses={401: _ERR, 403: _ERR, 404: _ERR, 409: _ERR, 422: _ERR},
)
def patch_rule(
    id: str,
    payload: RulePatch,
    request: Request,
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> ClassificationRule:
    return rule_service.patch_rule(
        db,
        request.app.state.settings.data_encryption_key,
        user_id=auth.user.id,
        rule_id=id,
        payload=payload,
    )
