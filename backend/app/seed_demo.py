"""导入合成演示数据，并对金额做机器核对。

用法（在 backend/ 目录下）：
    python -m app.seed_demo --username demo_a --password 你的密码
    python -m app.seed_demo --username demo_a --password 你的密码 --reset --yes

数据来源只有 fixtures/synthetic_ledger.json（全为合成数据）。脚本刻意做四件事：
1. 每笔交易先经过契约模型 contracts.Transaction 校验再加密入库，字段口径与 API 一致；
2. 去重摘要带 flow_type：SYN-ORDER-1 同时存在支出与退款两条，不能按订单号一刀切
   （docs/13 的要求）；
3. 核对时不看"本次插入"，而是从库里解密回读该月全部已确认交易，因此重复执行
   也得到同一结论，顺带验证了加密往返；
4. 与 fixtures 的 expected 逐项比对，不一致直接非 0 退出。
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import uuid
from pathlib import Path

from sqlalchemy import delete, select

from . import models
from .config import BACKEND_DIR, load_settings
from .contracts import Transaction as TransactionContract
from .crypto import dedupe_digest, decrypt_json, encrypt_json
from .db import build_engine, build_session_factory, session_scope, utcnow
from .security import hash_password
from .services.reporting import compute_totals

DEFAULT_FIXTURES = BACKEND_DIR.parent / "fixtures" / "synthetic_ledger.json"

_TOTAL_LABELS = {
    "income_fen": "收入",
    "gross_expense_fen": "支出合计",
    "refund_fen": "退款",
    "net_expense_fen": "净支出",
    "balance_fen": "收支差额",
}


def _yuan(fen: int) -> str:
    return f"{fen / 100:.2f}"


def _load_fixtures(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"找不到样例文件：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _get_or_create_user(db, username: str, password: str | None) -> models.User:
    user = db.scalar(select(models.User).where(models.User.username == username))
    if user is None:
        if not password:
            password = secrets.token_urlsafe(9)
            print(f"[注意] 未提供 --password，已生成一次性密码：{password}")
        user = models.User(
            id=str(uuid.uuid4()),
            username=username,
            password_hash=hash_password(password),
            is_active=True,
        )
        db.add(user)
        db.flush()
        print(f"[新建用户] {username} ({user.id})")
        return user

    if password:
        user.password_hash = hash_password(password)
        user.failed_login_count = 0
        user.locked_until = None
        print(f"[重设密码] {username}")
    else:
        print(f"[已有用户] {username} ({user.id})，密码未改动")
    return user


def _reset_user_data(db, user_id: str) -> None:
    # 顺序按外键依赖，先子后父
    db.execute(delete(models.CorrectionLog).where(models.CorrectionLog.user_id == user_id))
    db.execute(delete(models.Transaction).where(models.Transaction.user_id == user_id))
    db.execute(
        delete(models.ClassificationRule).where(models.ClassificationRule.user_id == user_id)
    )
    db.execute(delete(models.Budget).where(models.Budget.user_id == user_id))
    db.execute(delete(models.ImportBatch).where(models.ImportBatch.user_id == user_id))
    print("[重置] 已删除该用户的交易、批次、规则、预算与修正日志")


def _month_rows_from_db(db, user_id: str, month: str, key: str) -> list[dict]:
    """从库里解密回读，验证的是"数据库里真正存了什么"。"""
    stored = db.scalars(
        select(models.Transaction).where(
            models.Transaction.user_id == user_id,
            models.Transaction.month_index == month,
            models.Transaction.status == "confirmed",
        )
    ).all()
    return [decrypt_json(key, row.encrypted_payload) for row in stored]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导入合成演示账单")
    parser.add_argument("--username", required=True, help="演示账号，例如 demo_a")
    parser.add_argument("--password", default=None, help="登录密码；用户已存在时用于重设")
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--reset", action="store_true", help="先清空该用户的业务数据")
    parser.add_argument("--yes", action="store_true", help="配合 --reset 确认执行")
    args = parser.parse_args(argv)

    if args.reset and not args.yes:
        print("[拒绝] --reset 会删除该用户全部业务数据，需同时加 --yes", file=sys.stderr)
        return 2

    data = _load_fixtures(args.fixtures)
    settings = load_settings()
    key = settings.data_encryption_key
    month = data.get("month") or ""

    engine = build_engine(settings.database_url)
    factory = build_session_factory(engine)
    inserted = 0
    skipped = 0
    failure = False

    with session_scope(factory) as db:
        user = _get_or_create_user(db, args.username, args.password)
        if args.reset:
            _reset_user_data(db, user.id)

        # 每个平台一个批次：一次导入对应一个文件
        batches: dict[str, models.ImportBatch] = {}
        for source in sorted({item["source"] for item in data["transactions"]}):
            batch = models.ImportBatch(
                id=str(uuid.uuid4()),
                user_id=user.id,
                source=source,
                ingestion_method="file",
                status="completed",
                version=2,
                progress_current=0,
                progress_total=0,
                started_at=utcnow(),
                encrypted_filename=encrypt_json(
                    key, {"filename": f"synthetic_{source}.json", "synthetic": True}
                ),
            )
            db.add(batch)
            batches[source] = batch
        db.flush()

        for raw in data["transactions"]:
            digest = dedupe_digest(
                key,
                user.id,
                raw["source"],
                raw["flow_type"],
                raw["source_transaction_id"],
            )
            label = (
                f"{raw['source_transaction_id']:<16} {raw['source']:<7} "
                f"{raw['flow_type']:<9} {_yuan(raw['amount_fen']):>8}"
            )
            if db.scalar(
                select(models.Transaction.id).where(
                    models.Transaction.user_id == user.id,
                    models.Transaction.dedupe_digest == digest,
                )
            ):
                skipped += 1
                print(f"  [跳过] {label}  已存在")
                continue

            payload = TransactionContract(
                id=str(uuid.uuid4()),
                version=1,
                source=raw["source"],
                ingestion_method=raw["ingestion_method"],
                import_batch_id=batches[raw["source"]].id,
                source_transaction_id=raw["source_transaction_id"],
                occurred_at=raw["occurred_at"],
                amount_fen=raw["amount_fen"],
                currency=raw["currency"],
                flow_type=raw["flow_type"],
                merchant=raw["merchant"],
                description=raw["description"],
                category=raw["category"],
                classification_source="manual",
                classification_reason="合成演示数据，直接指定类别",
                status="confirmed",
            ).model_dump(mode="json")

            db.add(
                models.Transaction(
                    id=payload["id"],
                    user_id=user.id,
                    import_batch_id=payload["import_batch_id"],
                    version=1,
                    month_index=raw["occurred_at"][:7],
                    source=raw["source"],
                    flow_type=raw["flow_type"],
                    category=raw["category"],
                    status="confirmed",
                    dedupe_digest=digest,
                    encrypted_payload=encrypt_json(key, payload),
                )
            )
            inserted += 1
            print(f"  [入库] {label}")

        for source, batch in batches.items():
            count = sum(1 for item in data["transactions"] if item["source"] == source)
            batch.progress_current = count
            batch.progress_total = count

        for item in data.get("budgets", []):
            existing = db.scalar(
                select(models.Budget).where(
                    models.Budget.user_id == user.id,
                    models.Budget.month == month,
                    models.Budget.category == item["category"],
                )
            )
            token = encrypt_json(
                key,
                {"amount_fen": item["amount_fen"], "month": month, "category": item["category"]},
            )
            if existing is None:
                db.add(
                    models.Budget(
                        id=str(uuid.uuid4()),
                        user_id=user.id,
                        month=month,
                        category=item["category"],
                        encrypted_payload=token,
                    )
                )
            else:
                existing.encrypted_payload = token
        print(f"[预算] 已写入 {len(data.get('budgets', []))} 条（{month}）")
        user_id = user.id

    # 事务已提交，另开 session 回读：核对的是真正落库并已解密的数据
    with session_scope(factory) as db:
        rows = _month_rows_from_db(db, user_id, month, key)
        # 与 GET /api/reports/monthly 共用同一套口径，避免"核对过的数"和"接口返回的数"分叉
        actual = compute_totals(rows).model_dump()
        expected = (data.get("expected") or {}).get("totals") or {}

        print(f"\n本次入库 {inserted} 笔，跳过 {skipped} 笔；库内该月已确认 {len(rows)} 笔。")
        print("SYN-ORDER-1 的支出与退款是两条独立事件，故按 flow_type 区分去重。")
        if expected:
            print("\n金额核对（解密回读）：")
            for name, label in _TOTAL_LABELS.items():
                want = expected.get(name)
                got = actual.get(name)
                if want == got:
                    print(f"  {label:<6} {_yuan(got):>9}  一致")
                else:
                    failure = True
                    print(f"  {label:<6} {_yuan(got):>9}  不一致（fixtures 为 {want}）")

    if failure:
        print("[FAIL] 与 fixtures.expected 不一致，请检查 seed 逻辑", file=sys.stderr)
        return 1
    if expected:
        print("[OK] 与 fixtures.expected 完全一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
