"""为 demo_a 添加示例分类规则。"""

from __future__ import annotations

import sys
from pathlib import Path

# 添加 backend 到 sys.path
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import select
from app import models
from app.config import load_settings
from app.db import build_engine, build_session_factory
from app.services.transactions import _upsert_rule

DEFAULT_RULES = [
    # (source, merchant, category)
    ("alipay", "麦当劳(深圳南山店)", "dining"),
    ("alipay", "喜茶GO小程序", "dining"),
    ("alipay", "盒马鲜生", "shopping"),
    ("alipay", "中国石化加油站", "transport"),
    ("wechat", "瑞幸咖啡", "dining"),
    ("wechat", "滴滴出行", "transport"),
    ("wechat", "Steam游戏购买", "entertainment"),
    ("wechat", "国家电网电费充值", "housing"),
]


def main():
    settings = load_settings()
    engine = build_engine(settings.database_url)
    factory = build_session_factory(engine)

    with factory() as db:
        user = db.scalar(select(models.User).where(models.User.username == "demo_a"))
        if not user:
            print("未找到 demo_a 用户，请先运行 seed_demo")
            return 1

        print(f"找到用户 demo_a (id={user.id})，开始写入分类规则...")
        count = 0
        for source, merchant, category in DEFAULT_RULES:
            rule_id = _upsert_rule(
                db,
                settings.data_encryption_key,
                user_id=user.id,
                source=source,
                merchant=merchant,
                category=category,
            )
            print(f"  [{source}] 商户: {merchant:<16} -> 分类: {category:<12} (rule_id={rule_id})")
            count += 1

        db.commit()
        print(f"成功为 demo_a 写入 {count} 条分类规则！")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

