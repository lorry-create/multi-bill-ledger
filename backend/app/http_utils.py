"""HTTP 层的小工具。

`content_disposition` 单独抽出来，是因为原件下载（`/api/imports/{id}/original`）
和 CSV/PDF 导出都要给中文文件名做 RFC 5987 编码。写两份迟早漂移——一处改了
另一处忘，就会出现"原件能下、导出乱码"这种只在中文环境复现的怪问题。
"""

from __future__ import annotations

from urllib.parse import quote


def content_disposition(name: str, *, inline: bool = False) -> str:
    """中文文件名要给 RFC 5987 的 `filename*`，否则浏览器存成乱码。

    `filename=` 里的 ASCII 兜底串把非 ASCII 换成下划线，老浏览器也不会炸。
    """
    ascii_name = "".join(
        ch if 32 <= ord(ch) < 127 and ch not in '"\\' else "_" for ch in name
    )
    kind = "inline" if inline else "attachment"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name, safe='')}"


__all__ = ["content_disposition"]
