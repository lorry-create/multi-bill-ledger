"""建表与结构校验。

用法（在 backend/ 目录下）：
    python -m app.migrate            # 建表并记录版本（幂等）
    python -m app.migrate --check    # 只检查：表是否齐全、结构是否与模型一致
    python -m app.migrate --sql      # 打印 PostgreSQL DDL，用于评审或人工复核
    python -m app.migrate --drop     # 开发环境重建（生产环境直接拒绝）

设计取舍：T00 不引入 Alembic。表结构由 ORM 模型唯一描述，DDL 通过
`--sql` 从同一份模型导出，避免"手写 SQL 与模型不一致"。checksum 记录在
schema_migrations，字段改动而没升版本时，--check 会报漂移。
"""

from __future__ import annotations

import argparse
import hashlib
import sys

from sqlalchemy import inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from . import models  # noqa: F401  导入以注册全部表
from .config import load_settings
from .db import Base, build_engine, build_session_factory, session_scope

VERSION = "001"
NAME = "init"


def ddl_statements(dialect) -> list[str]:  # noqa: ANN001
    statements: list[str] = []
    for table in Base.metadata.sorted_tables:
        statements.append(str(CreateTable(table).compile(dialect=dialect)).strip())
        for index in sorted(table.indexes, key=lambda item: item.name or ""):
            statements.append(str(CreateIndex(index).compile(dialect=dialect)).strip())
    return statements


def ddl_checksum(dialect) -> str:
    joined = "\n".join(ddl_statements(dialect))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def expected_tables() -> set[str]:
    return set(Base.metadata.tables)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="建表 / 校验数据库结构")
    parser.add_argument("--check", action="store_true", help="只校验，不写库")
    parser.add_argument("--sql", action="store_true", help="输出 PostgreSQL DDL")
    parser.add_argument("--drop", action="store_true", help="删除所有表后重建（仅开发环境）")
    args = parser.parse_args(argv)

    settings = load_settings()
    dialect = postgresql.dialect()

    if args.sql:
        for statement in ddl_statements(dialect):
            print(statement + ";\n")
        return 0

    engine = build_engine(settings.database_url)
    factory = build_session_factory(engine)
    inspector = inspect(engine)

    if args.check:
        actual = set(inspector.get_table_names())
        missing = sorted(expected_tables() - actual)
        if missing:
            print(f"[FAIL] 缺表：{', '.join(missing)}", file=sys.stderr)
            return 1
        with session_scope(factory) as db:
            row = db.scalar(
                select(models.SchemaMigration).where(
                    models.SchemaMigration.version == VERSION
                )
            )
            if row is None:
                print(f"[FAIL] 缺少迁移记录 {VERSION}", file=sys.stderr)
                return 1
            current = ddl_checksum(engine.dialect)
            if current != row.checksum:
                print(
                    f"[FAIL] 结构漂移：记录 {row.checksum[:12]} / 当前 {current[:12]}；"
                    "改了模型就要新增迁移版本，不能静默改表",
                    file=sys.stderr,
                )
                return 1
        print(f"[OK] {len(actual)} 张表齐全，迁移 {VERSION} 校验通过")
        return 0

    if args.drop:
        if settings.is_production:
            print("[REFUSED] 生产环境禁止 --drop", file=sys.stderr)
            return 2
        Base.metadata.drop_all(engine)
        print("[OK] 已删除全部表")

    Base.metadata.create_all(engine)

    # checksum 用当前库的方言计算：不同方言的 DDL 文本不同，跨方言比较无意义
    current_dialect = engine.dialect
    checksum = ddl_checksum(current_dialect)
    with session_scope(factory) as db:
        row = db.scalar(
            select(models.SchemaMigration).where(models.SchemaMigration.version == VERSION)
        )
        if row is None:
            db.add(
                models.SchemaMigration(version=VERSION, name=NAME, checksum=checksum)
            )
            action = "已记录"
        else:
            row.checksum = checksum
            action = "已更新"

    print(
        f"[OK] 建表完成（{len(expected_tables())} 张），迁移 {VERSION} {action}，"
        f"checksum {checksum[:12]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
