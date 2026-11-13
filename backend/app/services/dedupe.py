"""去重与月份归属的唯一口径。

为什么要单独一个文件：同一笔交易会在三个地方被判断"是不是重复"——
处理批次时给草稿标 `duplicate_status`、确认入账时撞唯一约束、
重传同一份文件时的对照。三处只要算法有一点点不同，就会出现
"界面说重复、入账却成功"或者反过来的鬼故事，而且没人能快速定位。

两条纪律（来自 docs/13、docs/02）：
1. 摘要必须包含**事件性质**（flow_type）。同一订单号既可能是支出也可能是退款，
   只用订单号会把其中一条误删。
2. 没有可靠事件号时不冒充唯一事件号：退化为内容指纹，同类订单的多条记录
   仍然可能撞在一起，这时由解析侧标 `suspected` 交给用户决定，不在这里猜。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..crypto import dedupe_digest
from ..intelligence.normalize import normalize_merchant

CST = timezone(timedelta(hours=8))

# 摘要算法一旦变化必须换版本前缀，避免新旧摘要混在同一个唯一索引里互相误判
_DIGEST_VERSION = "v1"


def flow_value(flow_type: object) -> str:
    """FlowType 枚举或字符串都能取到稳定值（库里读出来的是字符串）。"""
    return str(getattr(flow_type, "value", flow_type))


def month_index(occurred_at: datetime) -> str:
    """按 Asia/Shanghai 归月。跨时区导入不能按 UTC 切，否则月初月末会串月。

    朴素时间（无 tzinfo）按上海时间解释——契约要求确认时带时区，这里只是
    兜底，不让一条数据把整批打挂。
    """
    if occurred_at.tzinfo is None:
        local = occurred_at.replace(tzinfo=CST)
    else:
        local = occurred_at.astimezone(CST)
    return local.strftime("%Y-%m")


def day_key(occurred_at: datetime) -> str:
    """内容指纹里的"同一天"按上海时区的自然日，和报表归月口径保持一致。"""
    return _local(occurred_at).strftime("%Y-%m-%d")


def _local(occurred_at: datetime) -> datetime:
    if occurred_at.tzinfo is None:
        return occurred_at.replace(tzinfo=CST)
    return occurred_at.astimezone(CST)


def row_digest(
    master: str,
    *,
    source: object,
    flow_type: object,
    source_transaction_id: str | None,
    occurred_at: datetime,
    amount_fen: int,
    merchant: str,
    description: str,
) -> str:
    """单笔交易的去重摘要。

    调用方必须传**最终**字段（用户在确认页改过的金额/类别/时间），否则
    确认阶段算出的摘要与批次处理阶段算出的不一致，重复判断就失效了。
    """
    source_value = str(getattr(source, "value", source))
    event = flow_value(flow_type)

    order_id = (source_transaction_id or "").strip()
    if order_id:
        parts = (_DIGEST_VERSION, "order", source_value, event, order_id)
    else:
        # 内容指纹：同平台 + 同方向 + 同一天 + 同金额 + 同商户 + 同说明
        parts = (
            _DIGEST_VERSION,
            "content",
            source_value,
            event,
            day_key(occurred_at),
            str(amount_fen),
            normalize_merchant(merchant),
            " ".join((description or "").split()),
        )
    return dedupe_digest(master, *parts)
