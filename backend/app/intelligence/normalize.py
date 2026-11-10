"""商户名标准化。

docs/13 只规定三步：NFKC、trim、合并空白、casefold。这里严格照做，不加"智能"处理
（比如剥掉「支付宝-」前缀），因为规则匹配要求可预测——多做一步就会让用户建的
规则在下次导入时突然不命中，而用户看不到原因。
"""

from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"\s+")
# 零宽字符与 BOM：从网页或聊天窗口复制商户名时经常夹带，肉眼不可见但会让规则失配
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff\u00a0"), " ")


def normalize_merchant(raw: str) -> str:
    if not raw:
        return ""
    text = unicodedata.normalize("NFKC", raw)
    text = text.translate(_INVISIBLE)
    text = _WS.sub(" ", text).strip()
    return text.casefold()
