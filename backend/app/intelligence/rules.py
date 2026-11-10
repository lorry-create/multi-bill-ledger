"""通用关键词分类规则。

这是"零外部依赖也能跑通闭环"的那一层：不调模型、不联网、结果确定可复现。
它同时是 D 接 DeepSeek 之后仍然存在的兜底——模型超时或返回非法时，交易不能
卡在 pending 里永远不可用，得有一条诚实标着 `general_rule` 的路径。

设计取舍：
- **最长匹配优先**，不是"表里排前面的优先"。「美团买菜」同时命中「美团」和「买菜」，
  按长度取「美团买菜」才对；按表序会随人工排版顺序漂移，无法解释。
- 命中不了就返回 None，由调用方置 `pending` 并写 Issue。绝不返回一个"猜的"类别，
  因为错分类比未分类更难被用户发现。
"""

from __future__ import annotations

from ..contracts import Category, FlowType

# 词表按类别分组。同类别内顺序无所谓（按长度择优），但不要放两个互相包含的词
# 却指望它们给出不同结果。
_KEYWORDS: dict[Category, tuple[str, ...]] = {
    Category.dining: (
        "餐饮", "美食", "餐厅", "饭店", "食堂", "小吃", "快餐", "面馆", "火锅", "烧烤",
        "咖啡", "奶茶", "茶饮", "烘焙", "面包", "甜品", "外卖",
        "美团外卖", "饿了么", "美团", "大众点评",
        "麦当劳", "肯德基", "德克士", "汉堡王", "必胜客", "星巴克", "瑞幸", "库迪",
        "喜茶", "奈雪", "蜜雪冰城", "茶百道", "古茗", "沪上阿姨", "海底捞", "西贝",
        "便利蜂", "全家", "罗森", "711", "7-11",
    ),
    Category.transport: (
        "地铁", "公交", "轨道交通", "出租车", "网约车", "打车", "顺风车", "单车",
        "高铁", "火车票", "机票", "航空", "12306", "滴滴", "高德打车", "曹操出行",
        "T3出行", "哈啰", "青桔", "美团单车", "加油", "中石化", "中石油", "充电桩",
        "停车", "高速", "ETC", "过路费",
    ),
    Category.shopping: (
        "超市", "便利店", "百货", "商场", "购物中心", "淘宝", "天猫", "京东", "拼多多",
        "唯品会", "苏宁", "沃尔玛", "家乐福", "永辉", "华润万家", "盒马", "山姆",
        "名创优品", "屈臣氏", "优衣库", "无印良品", "小米之家", "苹果专卖",
    ),
    Category.housing: (
        "房租", "租金", "物业", "物业管理", "水费", "电费", "燃气", "天然气", "供暖",
        "宽带", "电信", "移动通信", "中国联通", "话费", "网费", "中介费",
    ),
    Category.entertainment: (
        "电影", "影城", "影院", "KTV", "游戏", "网吧", "演出", "话剧", "演唱会",
        "展览", "门票", "旅游", "酒店", "民宿", "健身", "瑜伽",
        "腾讯视频", "爱奇艺", "优酷", "哔哩哔哩", "网易云音乐", "QQ音乐", "Steam",
    ),
    Category.health: (
        "医院", "诊所", "门诊", "挂号", "体检", "药房", "药店", "大药房", "医药",
        "口腔", "牙科", "眼科", "医疗", "卫生服务",
    ),
    Category.education: (
        "学费", "培训", "课程", "网课", "教育", "书店", "书城", "当当", "文具",
        "考试", "报名费", "驾校", "图书馆",
    ),
    Category.salary: (
        "工资", "薪资", "薪水", "奖金", "绩效", "津贴", "补助", "劳务", "薪金",
    ),
}

# 收入分两步看：先认工资（计入 salary），其余归 other。
# 不能把所有收入关键词都映射到 salary——"好友转入红包"不是工资，
# 归错会让月报里的"工资收入"虚高，而用户很难一眼看出问题。
_SALARY_KEYWORDS: tuple[str, ...] = (
    "工资", "薪资", "薪水", "薪金", "奖金", "绩效", "津贴", "补助", "劳务费", "代发",
)
_OTHER_INCOME_KEYWORDS: tuple[str, ...] = (
    "红包", "利息", "分红", "报销", "返现", "转入", "退款", "收益", "结算",
)

_FLOW_LABELS = {
    FlowType.income: "收入",
    FlowType.expense: "支出",
    FlowType.refund: "退款",
    FlowType.transfer: "转账",
    FlowType.repayment: "还款",
}


def _longest_hit(text: str, words: tuple[str, ...]) -> str | None:
    """找出在 text 中出现的最长关键词。同长度取词表序靠前者，保证结果稳定。"""
    best: str | None = None
    for word in words:
        if word and word in text:
            if best is None or len(word) > len(best):
                best = word
    return best


def classify_by_keywords(
    merchant: str, description: str, flow_type: FlowType | None
) -> tuple[Category, str] | None:
    """按通用规则分类。命中返回 (类别, 依据)，未命中返回 None。"""
    haystack = f"{merchant} {description}"

    if flow_type == FlowType.income:
        hit = _longest_hit(haystack, _SALARY_KEYWORDS)
        if hit:
            return Category.salary, f"收入类通用规则命中「{hit}」"
        other = _longest_hit(haystack, _OTHER_INCOME_KEYWORDS)
        if other:
            return Category.other, f"非工资收入（命中「{other}」），归入其他"
        # 收入但看不出性质：归 other，不硬塞进 salary，否则月报"工资收入"会虚高
        return Category.other, "收入类未命中工资关键词，归入其他"

    # 支出 / 退款 / 转账 / 还款：按类别词表择优
    best: tuple[Category, str] | None = None
    for category, words in _KEYWORDS.items():
        hit = _longest_hit(haystack, words)
        if hit is not None and (best is None or len(hit) > len(best[1])):
            best = (category, hit)

    if best is not None:
        category, hit = best
        label = _FLOW_LABELS.get(flow_type) if flow_type else ""
        prefix = f"{label}类" if label else ""
        return category, f"{prefix}通用规则命中「{hit}」"
    return None
