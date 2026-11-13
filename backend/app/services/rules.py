"""个人商户分类规则的读取与修改。

闭环第五环（用户修正反馈）的落地位置：用户在账单页改对一类的分类并勾"记住商户"，
规则在这里被读出来、也可以在这里被停用或改类。对应 docs/01 的 F07、docs/08 的 A07。

四条纪律：

1. **停用不重写历史账单**。规则只影响后续自动分类，已入账交易保持原样。
   契约原话："停用不重写历史交易"。要改历史账去 `PATCH /api/transactions/{id}`。
2. **读全部，包括已停用的**。契约要求 listRules 返回本人全部规则并按
   `source` 再 `merchant_normalized` 升序。只返回启用的会让用户在页面上
   看不到自己停过什么，等于无法重新启用。
3. **`enabled` 以明文列为唯一真相**。表上 `enabled` 是明文布尔列（导入时要在
   SQL 层筛 `enabled IS TRUE`，不能为它解密整表），加密区里的 `enabled`
   属历史遗留冗余字段，写入时同步以防水位漂移，读取时一律以明文列为准。
4. **单条规则解不开不能拖垮整页**。跳过并记日志，与列表/月报同策略；
   真正的止血手段是密钥管理，不是在这里假装正常。
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..contracts import (
    ClassificationRule,
    ErrorDetails,
    FieldError,
    RuleList,
    RulePatch,
    Source,
)
from ..crypto import CryptoError, decrypt_json, encrypt_json
from ..db import utcnow
from ..errors import ApiError

logger = logging.getLogger("app.services.rules")


def _not_found() -> ApiError:
    # 别人的规则一律 404：403 会告诉调用方"这个 ID 确实存在"
    return ApiError("RESOURCE_NOT_FOUND", 404, "资源不存在", ErrorDetails())


def _unprocessable(field: str, code: str, message: str) -> ApiError:
    return ApiError(
        "VALIDATION_ERROR",
        422,
        message,
        details=ErrorDetails(fields=[FieldError(field=field, row_id=None, code=code, message=message)]),
    )


def _to_contract(record: models.ClassificationRule, payload: dict) -> ClassificationRule | None:
    """把库里的行 + 解密载荷变成契约对象。类别码非法时返回 None 交给调用方跳过。"""
    try:
        category = payload["category"]
    except KeyError:
        logger.warning("规则 %s 载荷缺少 category，已跳过", record.id)
        return None
    try:
        return ClassificationRule(
            id=record.id,
            version=record.version,
            source=Source(record.source),
            merchant_normalized=str(payload.get("merchant_normalized") or ""),
            category=category,
            # 明文列是唯一真相
            enabled=bool(record.enabled),
        )
    except (ValueError, TypeError):
        # 平台码或类别码已被废弃/写坏：跳过这一条，不让整页 500
        logger.warning("规则 %s 的平台或类别码非法，已跳过", record.id)
        return None


def list_rules(db: Session, user_id: str, key: str) -> RuleList:
    """本人全部规则（含已停用），按 source 再 merchant_normalized 升序。"""
    records = db.scalars(
        select(models.ClassificationRule).where(models.ClassificationRule.user_id == user_id)
    ).all()

    items: list[ClassificationRule] = []
    for record in records:
        try:
            payload = decrypt_json(key, record.encrypted_payload)
        except CryptoError:
            logger.warning("规则 %s 载荷无法解密，已跳过列表返回", record.id)
            continue
        item = _to_contract(record, payload)
        if item is not None:
            items.append(item)

    # 契约：source 再 merchant_normalized 升序。商户名在加密区，
    # 只能解密后排序（规则通常几十条，可接受）
    items.sort(key=lambda rule: (rule.source.value, rule.merchant_normalized))
    return RuleList(items=items)


def load_owned(db: Session, user_id: str, rule_id: str) -> models.ClassificationRule:
    record = db.get(models.ClassificationRule, rule_id)
    if record is None or record.user_id != user_id:
        raise _not_found()
    return record


def patch_rule(
    db: Session,
    key: str,
    *,
    user_id: str,
    rule_id: str,
    payload: RulePatch,
) -> ClassificationRule:
    """改类别或停用/启用。不碰 `transactions` 表，历史账单保持原样。"""
    # 契约用 anyOf 要求"至少提供 enabled 或 category"；pydantic 模型两个字段都可为
    # None，这条约束得在这里补上，否则空请求会被当成"什么都没改"悄悄成功
    if payload.enabled is None and payload.category is None:
        raise _unprocessable(
            "enabled", "RULE_PATCH_EMPTY", "至少提供 enabled 或 category 之一"
        )

    record = load_owned(db, user_id, rule_id)

    if payload.expected_version != record.version:
        raise ApiError(
            "VERSION_CONFLICT",
            409,
            "规则已被其他操作修改",
            ErrorDetails(current_version=record.version),
        )

    try:
        stored = decrypt_json(key, record.encrypted_payload)
    except CryptoError:
        # 解不开就没法安全合并（不知道原 merchant_normalized 是什么），
        # 直接报 409 让用户重新读取，而不是猜一个值覆盖回去
        raise ApiError(
            "VERSION_CONFLICT",
            409,
            "规则内容无法读取，请刷新后重试",
            ErrorDetails(current_version=record.version),
        ) from None

    category_value = stored.get("category")
    if payload.category is not None:
        category_value = payload.category.value

    enabled_value = bool(record.enabled)
    if payload.enabled is not None:
        enabled_value = payload.enabled

    # 加密区与明文列同步写：明文列是读取真相，加密区补一致以免两处水位漂移
    record.encrypted_payload = encrypt_json(
        key,
        {
            "merchant_normalized": stored.get("merchant_normalized"),
            "category": category_value,
            "enabled": enabled_value,
        },
    )
    record.enabled = enabled_value
    record.version += 1
    record.updated_at = utcnow()

    db.commit()
    db.refresh(record)

    item = _to_contract(record, decrypt_json(key, record.encrypted_payload))
    if item is None:  # pragma: no cover - 刚写入的值不可能非法
        raise _unprocessable("category", "RULE_CATEGORY_INVALID", "类别代码不合法")
    return item


__all__ = ["list_rules", "load_owned", "patch_rule"]
