"""按配置选择智能模块实现。

内置两档，没有自动降级：

- `local-rapidocr`（默认）：本地 OCR 与规则分类；
- `fallback-rules`：只解析文件和规则分类，截图明确报错。

也可以按点分路径接入其他实现（`intelligence.custom:Provider`）。

**故意不提供"真实实现失败就悄悄换成 fallback"**。原因：那样分类结果会标成
`general_rule` 却让所有人以为走了模型，准确率报表全错，属于 docs/08 A06 说的伪成功。
要降级就显式改配置，让 `classification_source` 说实话。
"""

from __future__ import annotations

import importlib

from .base import IntelligenceProvider
from .fallback import FallbackIntelligence
from .ocr import LocalOCRIntelligence

DEFAULT_PROVIDER = "local-rapidocr"

# 内置实现注册表；D 的实现通过点分路径按需导入，不写死 import 避免循环依赖
_BUILTIN: dict[str, type] = {DEFAULT_PROVIDER: LocalOCRIntelligence, "fallback-rules": FallbackIntelligence}


class ProviderNotAvailable(RuntimeError):
    """配置指定的实现不存在。启动阶段就失败，不要运行到一半才发现分类走不通。"""


def build_intelligence(name: str | None = None) -> IntelligenceProvider:
    """按名字构造实现。点分路径形如 `package.module:ClassName`。"""
    key = (name or DEFAULT_PROVIDER).strip() or DEFAULT_PROVIDER

    if key in _BUILTIN:
        return _BUILTIN[key]()

    if ":" not in key:
        raise ProviderNotAvailable(
            f"未知的智能模块实现：{key}（可用内置：{', '.join(sorted(_BUILTIN))}；"
            "自定义实现需写成 包.模块:类名）"
        )

    module_path, _, class_name = key.partition(":")
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise ProviderNotAvailable(f"无法导入智能模块 {module_path}：{exc}") from exc
    try:
        factory = getattr(module, class_name)
    except AttributeError as exc:
        raise ProviderNotAvailable(f"模块 {module_path} 中没有 {class_name}") from exc

    instance = factory()
    if not isinstance(instance, IntelligenceProvider):
        # runtime_checkable 的 Protocol 只校验方法名是否存在，能拦住"少实现一个方法"
        raise ProviderNotAvailable(f"{key} 未实现 IntelligenceProvider 要求的全部方法")
    return instance
