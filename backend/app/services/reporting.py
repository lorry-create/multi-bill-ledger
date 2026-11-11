"""月度报表的确定性计算。

唯一口径来源。`seed_demo` 的金额核对和 `GET /api/reports/monthly` 都调这里，
不允许各算一套——否则"核对通过的数"和"接口返回的数"迟早不一致，而且
没人能第一时间发现（docs/13：报告不维护另一套容易过期的累计总数）。

三条硬约束，全部来自契约与验收文档：
1. 只统计 `status == confirmed` 的交易；
2. 每次按用户 + 月份现算，不建汇总表；
3. `balance_fen` 是「收支差额」，**不是账户余额**，字段名和文档都不许混。
"""

from __future__ import annotations

import calendar
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..contracts import (
    BudgetStatus,
    Category,
    FlowType,
    MonthlyReport,
    MonthlyReportDailyTrendItem,
    MonthlyReportExpenseByCategoryItem,
    ResolvedCategory,
    Totals,
)
from ..crypto import CryptoError, decrypt_json
from ..errors import ApiError


def compute_totals(rows: list[dict]) -> Totals:
    """按 flow_type 汇总。退款是净支出的减项，不是收入。"""
    income = sum(r["amount_fen"] for r in rows if r["flow_type"] == FlowType.income)
    gross = sum(r["amount_fen"] for r in rows if r["flow_type"] == FlowType.expense)
    refund = sum(r["amount_fen"] for r in rows if r["flow_type"] == FlowType.refund)
    net = gross - refund
    return Totals(
        income_fen=income,
        gross_expense_fen=gross,
        refund_fen=refund,
        net_expense_fen=net,
        balance_fen=income - net,
    )


def month_days(month: str) -> list[date]:
    """YYYY-MM → 该月每个自然日。daily_trend 要求"无交易日各项为 0"，所以必须补满。"""
    year, mon = (int(part) for part in month.split("-"))
    last = calendar.monthrange(year, mon)[1]
    return [date(year, mon, day) for day in range(1, last + 1)]


def _category_order() -> dict[str, int]:
    """按契约里 ResolvedCategory 的声明顺序排，保证同一份数据每次顺序一致。"""
    return {item.value: index for index, item in enumerate(ResolvedCategory)}


def build_monthly_report(db: Session, user_id: str, month: str, key: str) -> MonthlyReport:
    """从库里解密计算整月报表。"""
    stored = db.scalars(
        select(models.Transaction).where(
            models.Transaction.user_id == user_id,
            models.Transaction.month_index == month,
            models.Transaction.status == "confirmed",
        )
    ).all()

    rows: list[dict] = []
    for record in stored:
        try:
            rows.append(decrypt_json(key, record.encrypted_payload))
        except CryptoError as exc:
            raise ApiError("REPORT_DATA_UNAVAILABLE", 503, "部分账单无法读取，请检查数据密钥或备份") from exc

    totals = compute_totals(rows)

    by_category: dict[str, int] = {}
    daily: dict[date, dict[str, int]] = {}
    net_by_category: dict[str, int] = {}

    for row in rows:
        flow = row["flow_type"]
        amount = row["amount_fen"]
        category = row.get("category") or Category.pending.value

        if flow == FlowType.expense:
            by_category[category] = by_category.get(category, 0) + amount
            net_by_category[category] = net_by_category.get(category, 0) + amount
        elif flow == FlowType.refund:
            net_by_category[category] = net_by_category.get(category, 0) - amount

        day = _day_of(row.get("occurred_at"))
        if day is None:
            continue
        bucket = daily.setdefault(
            day,
            {"income_fen": 0, "gross_expense_fen": 0, "refund_fen": 0},
        )
        if flow == FlowType.income:
            bucket["income_fen"] += amount
        elif flow == FlowType.expense:
            bucket["gross_expense_fen"] += amount
        elif flow == FlowType.refund:
            bucket["refund_fen"] += amount

    order = _category_order()
    expense_items: list[MonthlyReportExpenseByCategoryItem] = []
    for cat_value, amount in sorted(by_category.items(), key=lambda pair: order.get(pair[0], 999)):
        # 契约：仅返回毛支出大于 0 的类别
        if amount <= 0:
            continue
        try:
            category = Category(cat_value)
        except ValueError:
            # 库里存在已废弃的类别码时跳过该条，不让整张月报 500
            continue
        expense_items.append(
            MonthlyReportExpenseByCategoryItem(category=category, amount_fen=amount)
        )

    trend = []
    for day in month_days(month):
        bucket = daily.get(day, {"income_fen": 0, "gross_expense_fen": 0, "refund_fen": 0})
        trend.append(
            MonthlyReportDailyTrendItem(
                date=day,
                income_fen=bucket["income_fen"],
                gross_expense_fen=bucket["gross_expense_fen"],
                refund_fen=bucket["refund_fen"],
                net_expense_fen=bucket["gross_expense_fen"] - bucket["refund_fen"],
            )
        )

    return MonthlyReport(
        month=month,
        totals=totals,
        expense_by_category=expense_items,
        daily_trend=trend,
        budgets=_budget_statuses(db, user_id, month, key, net_by_category, order),
    )


def _day_of(value: str | None) -> date | None:
    """从 ISO 时间串取日期。按 Asia/Shanghai 归月已在入库前完成，这里只切日期部分。"""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _budget_statuses(
    db: Session,
    user_id: str,
    month: str,
    key: str,
    net_by_category: dict[str, int],
    order: dict[str, int],
) -> list[BudgetStatus]:
    records = db.scalars(
        select(models.Budget).where(
            models.Budget.user_id == user_id,
            models.Budget.month == month,
        )
    ).all()

    items: list[BudgetStatus] = []
    for record in records:
        try:
            payload = decrypt_json(key, record.encrypted_payload)
        except CryptoError as exc:
            raise ApiError("BUDGET_DATA_UNAVAILABLE", 503, "预算数据无法读取，请检查数据密钥或备份") from exc
        budget_fen = int(payload.get("amount_fen", 0))
        # 用净支出而不是毛支出：退款回到预算里，才符合"这个月还能花多少"的直觉（A10）
        spent = net_by_category.get(record.category, 0)
        try:
            category = ResolvedCategory(record.category)
        except ValueError:
            # pending 或历史类别码不能出现在预算里（契约要求 ResolvedCategory）
            continue
        items.append(
            BudgetStatus(
                category=category,
                budget_fen=max(0, budget_fen),
                spent_fen=spent,
                remaining_fen=budget_fen - spent,
                over_fen=max(0, spent - budget_fen),
            )
        )
    items.sort(key=lambda item: order.get(item.category.value, 999))
    return items
