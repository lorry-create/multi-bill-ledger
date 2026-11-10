"""解析探测工具：把一份账单文件跑一遍解析+分类，打印结果供人工核对。

用途（docs/08 A02 要求"两平台实际文件，人工核对条数金额"）：

    cd backend
    python -m app.tools.parse_probe ../data/private/alipay_2026-10.csv --source alipay

它不连数据库、不写任何文件，只回答三个问题：认出几条、每条多少钱、哪些字段有问题。
真实账单永远走这个命令核对，不要靠"页面上看着对"。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..contracts import FlowType
from ..intelligence import IntelligenceFailure, build_intelligence


def _yuan(fen: int | None) -> str:
    return "   ?  " if fen is None else f"{fen / 100:.2f}"


def _flow(value: FlowType | None) -> str:
    return value.value if value else "?"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="解析账单文件并打印供人工核对")
    parser.add_argument("path", type=Path, help="账单文件路径（.csv/.xlsx）")
    parser.add_argument(
        "--source",
        default="alipay",
        choices=("alipay", "wechat"),
        help="平台；标错也能按内容识别，但会给出提示",
    )
    parser.add_argument("--provider", default=None, help="智能模块实现，默认用配置值")
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"文件不存在：{args.path}", file=sys.stderr)
        return 2

    provider = build_intelligence(args.provider)
    data = args.path.read_bytes()

    try:
        result = provider.parse_bill_file(data, args.path.name, args.source)
    except IntelligenceFailure as exc:
        print(f"[解析失败] {exc.code}: {exc.message}", file=sys.stderr)
        return 1

    classified = {
        item.row_id: item
        for item in provider.classify_transactions(result.rows, [], use_llm=False)
    }

    print(f"实现：{provider.name}    文件：{args.path.name}    平台声明：{args.source}")
    print(f"解析出 {len(result.rows)} 条草稿，{len(result.issues)} 条问题\n")
    header = f"{'行号':<14} {'时间':<17} {'流向':<8} {'金额':>9} {'类别':<14} {'商户'}"
    print(header)
    print("-" * len(header))

    totals: dict[str, int] = {}
    for row in result.rows:
        item = classified.get(row.row_id)
        category = item.category.value if item else "?"
        occurred = row.occurred_at.strftime("%Y-%m-%d %H:%M") if row.occurred_at else "-"
        print(
            f"{row.row_id:<14} {occurred:<17} {_flow(row.flow_type):<8} "
            f"{_yuan(row.amount_fen):>9} {category:<14} {row.merchant[:20]}"
        )
        if row.flow_type and row.amount_fen:
            totals[row.flow_type.value] = totals.get(row.flow_type.value, 0) + row.amount_fen

    print("\n按流向合计：")
    for flow in ("income", "expense", "refund"):
        print(f"  {flow:<8} {_yuan(totals.get(flow, 0)):>10}")

    if result.issues:
        print("\n问题清单：")
        for issue in result.issues:
            print(f"  [{issue.code}] {issue.row_id or '-'} {issue.field or '-'} {issue.message}")

    print("\n请与平台页面显示的条数和金额逐项比对；不一致时不要继续导入。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
