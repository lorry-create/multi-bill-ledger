#!/usr/bin/env python3
"""从 contracts/openapi.json 生成 backend/app/contracts.py（Pydantic v2 共用模型）。

为什么要有这个脚本
- AGENTS.md 要求 D 从 app.contracts 导入共用模型，不得另造金额字段或枚举；
  H 与 F 也必须使用同一份字段形状。手工抄 35 个模型必然与契约漂移。
- 契约改了却只有一端跟着改，是这类三人协作最容易翻车的地方。一条命令同步 +
  --check 进 CI，可以把「生成物被手改」变成一次失败的检查，而不是一次线上 422。

零第三方依赖：只读契约、只写生成物。
用法：
    python tools/gen_pydantic_models.py                 # 生成到 backend/app/contracts.py
    python tools/gen_pydantic_models.py --out some.py   # 生成到指定路径
    python tools/gen_pydantic_models.py --check         # 只检查是否漂移，退出码 1 表示漂移
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = ROOT / "contracts" / "openapi.json"
DEFAULT_OUT = ROOT / "backend" / "app" / "contracts.py"

SCALARS = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
}

FORMATS = {
    ("string", "date-time"): "_datetime",
    ("string", "date"): "_date",
}

_MISSING = object()


def pascal(value: str) -> str:
    parts = re.split(r"[^0-9a-zA-Z]+", value)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def q(value) -> str:
    """JSON 字符串字面量，同时是合法的 Python 字面量（含中文不转义）。"""
    return json.dumps(value, ensure_ascii=False)


def pylit(value) -> str:
    """把 JSON 值写成合法的 Python 字面量（None/True/False 不能写成 null/true/false）。"""
    if value is None:
        return "None"
    if value is True:
        return "True"
    if value is False:
        return "False"
    if isinstance(value, str):
        return q(value)
    if isinstance(value, (int, float)):
        return repr(value)
    return json.dumps(value, ensure_ascii=False)


def docstring(text: str) -> str:
    cleaned = " ".join((text or "").split())
    cleaned = cleaned.replace("\\", " ").replace('"', "'")
    return cleaned


class Generator:
    def __init__(self, spec: dict) -> None:
        self.spec = spec
        self.schemas: dict = spec["components"]["schemas"]
        self.version: str = spec["info"]["version"]
        self.order: list[tuple[str, str]] = []
        self._emitted: set[str] = set()
        self.model_names: list[str] = []
        self.enum_names: list[str] = []
        # 内联枚举若与某个顶层枚举取值完全一致，直接复用该枚举，避免同一语义出现两种写法
        self.enum_index: dict[frozenset, str] = {}
        for name, schema in self.schemas.items():
            if "enum" in schema and "properties" not in schema:
                self.enum_index.setdefault(frozenset(v for v in schema["enum"] if v is not None), name)

    # ---------- 引用 ----------
    @staticmethod
    def ref_name(ref: str) -> str:
        return ref.rsplit("/", 1)[-1]

    def collect_refs(self, node, acc: set[str]) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str):
                acc.add(self.ref_name(ref))
            for value in node.values():
                self.collect_refs(value, acc)
        elif isinstance(node, list):
            for item in node:
                self.collect_refs(item, acc)

    def topo(self) -> list[str]:
        """让被引用的顶层模型先定义，避免生成不可执行的前向引用。"""
        done: list[str] = []
        seen: set[str] = set()
        stack: set[str] = set()

        def visit(name: str) -> None:
            if name in seen or name in stack:
                return
            stack.add(name)
            refs: set[str] = set()
            self.collect_refs(self.schemas[name], refs)
            for dep in sorted(refs):
                if dep in self.schemas and dep != name:
                    visit(dep)
            stack.discard(name)
            seen.add(name)
            done.append(name)

        for name in self.schemas:
            visit(name)
        return done

    # ---------- 类型 ----------
    def literal_of(self, values: list) -> str:
        items = [q(v) for v in values if v is not None]
        if not items:
            return "str"
        reused = self.enum_index.get(frozenset(v for v in values if v is not None))
        if reused:
            return reused
        return "Literal[" + ", ".join(items) + "]"

    def constraints(self, prop: dict) -> dict:
        out: dict = {}
        if "minimum" in prop:
            out["ge"] = prop["minimum"]
        if "maximum" in prop:
            out["le"] = prop["maximum"]
        if "exclusiveMinimum" in prop:
            out["gt"] = prop["exclusiveMinimum"]
        if "exclusiveMaximum" in prop:
            out["lt"] = prop["exclusiveMaximum"]
        if "minLength" in prop:
            out["min_length"] = prop["minLength"]
        elif "minItems" in prop:
            out["min_length"] = prop["minItems"]
        if "maxLength" in prop:
            out["max_length"] = prop["maxLength"]
        elif "maxItems" in prop:
            out["max_length"] = prop["maxItems"]
        if "pattern" in prop:
            out["pattern"] = prop["pattern"]
        return out

    def type_of(self, prop: dict, owner: str, hint: str) -> str:
        if "$ref" in prop:
            return self.ref_name(prop["$ref"])

        if "const" in prop:
            return f"Literal[{q(prop['const'])}]"

        raw = prop.get("type")
        if raw is None:
            if "enum" in prop:
                return self.literal_of(prop["enum"])
            return "str" if "properties" not in prop else "dict"

        names = raw if isinstance(raw, list) else [raw]
        nullable = "null" in names or ("enum" in prop and None in prop.get("enum", []))
        names = [n for n in names if n != "null"] or ["string"]

        if names[0] == "array":
            inner = self.type_of(prop.get("items") or {}, owner, hint + "Item")
            base = f"list[{inner}]"
        elif names[0] == "object":
            child = f"{owner}{pascal(hint)}"
            self.emit_object(child, prop)
            base = child
        elif names[0] == "string" and "enum" in prop:
            base = self.literal_of(prop["enum"])
        elif names[0] == "integer" and hint.endswith("_fen"):
            # 金额一律严格整数：不接受 "2300" 或 2300.0，避免浮点/字符串静默转换
            base = "StrictInt"
        else:
            base = FORMATS.get((names[0], prop.get("format")), SCALARS.get(names[0], names[0]))

        return f"Optional[{base}]" if nullable else base

    # ---------- 生成 ----------
    def emit_enum(self, name: str, schema: dict) -> None:
        if name in self._emitted:
            return
        self._emitted.add(name)
        description = docstring(schema.get("description", ""))
        lines = [f"class {name}(str, Enum):"]
        if description:
            lines.append(f'    """{description}"""')
        lines.append("")
        for value in schema.get("enum", []):
            if value is None:
                continue
            member = value if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) else pascal(value)
            lines.append(f"    {member} = {q(value)}")
        self.order.append((name, "\n".join(lines)))
        self.enum_names.append(name)

    def emit_object(self, name: str, schema: dict) -> None:
        if name in self._emitted:
            return
        self._emitted.add(name)

        props: dict = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        body: list[str] = []

        for prop_name, prop in props.items():
            annotation = self.type_of(prop, name, prop_name)
            default = prop.get("default", _MISSING)
            args: list[str] = []

            if prop_name in required:
                args.append("..." if default is _MISSING else f"default={pylit(default)}")
            else:
                if not annotation.startswith("Optional["):
                    annotation = f"Optional[{annotation}]"
                args.append(f"default={pylit(default if default is not _MISSING else None)}")

            for key, value in self.constraints(prop).items():
                args.append(f"{key}={q(value)}" if key == "pattern" else f"{key}={value}")

            description = prop.get("description")
            if description:
                args.append(f"description={q(docstring(description))}")

            body.append(f"    {prop_name}: {annotation} = Field({', '.join(args)})")

        lines = [f"class {name}(BaseModel):"]
        description = docstring(schema.get("description", ""))
        if description:
            lines.append(f'    """{description}"""')
        if schema.get("additionalProperties") is False:
            lines.append('    model_config = ConfigDict(extra="forbid")')
        if body:
            if description or schema.get("additionalProperties") is False:
                lines.append("")
            lines.extend(body)
        elif not description and schema.get("additionalProperties") is not False:
            lines.append("    pass")

        self.order.append((name, "\n".join(lines)))
        self.model_names.append(name)

    def render(self) -> str:
        for name in self.topo():
            schema = self.schemas[name]
            if "enum" in schema and "properties" not in schema and schema.get("type") in (None, "string"):
                self.emit_enum(name, schema)
            else:
                self.emit_object(name, schema)

        header = (
            '"""共用模型：由 tools/gen_pydantic_models.py 从 contracts/openapi.json 生成。\n\n'
            f"契约版本：{self.version}\n"
            "不要手改本文件。改契约后执行：python tools/gen_pydantic_models.py\n"
            "D 侧（backend/app/intelligence）从这里导入 ParseResult、TransactionDraft 等类型，\n"
            "不得另定义一套金额单位或类别枚举。\n"
            '"""\n\n'
            "from datetime import date as _date, datetime as _datetime\n"
            "from enum import Enum\n"
            "from typing import Literal, Optional\n\n"
            "from pydantic import BaseModel, ConfigDict, Field, StrictInt\n\n"
            f'CONTRACT_VERSION = "{self.version}"\n\n'
            "__all__ = [\n"
            + "".join(f'    "{name}",\n' for name in self.enum_names + self.model_names)
            + "]\n"
        )

        chunks = [header]
        for _, code in self.order:
            chunks.append(code + "\n")

        if self.model_names:
            chunks.append(
                "# 兜底：确保跨模型引用在运行时完成解析\n"
                "_MODELS = (\n"
                + "".join(f"    {name},\n" for name in self.model_names)
                + ")\n"
                "for _model in _MODELS:\n"
                "    _model.model_rebuild()\n"
            )

        return "\n".join(chunks)


def build(spec_path: Path) -> str:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    return Generator(spec).render()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="从 OpenAPI 契约生成 Pydantic 共用模型")
    parser.add_argument("--contract", default=str(CONTRACT_PATH), help="契约路径")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="输出路径")
    parser.add_argument("--check", action="store_true", help="只校验，不写文件")
    args = parser.parse_args(argv)

    contract = Path(args.contract)
    out = Path(args.out)
    if not contract.exists():
        print(f"[gen] 找不到契约：{contract}", file=sys.stderr)
        return 2

    generated = build(contract)

    if args.check:
        if not out.exists():
            print(f"[gen] 生成物不存在：{out}", file=sys.stderr)
            return 1
        current = out.read_text(encoding="utf-8")
        if current == generated:
            print(f"[gen] OK 生成物与契约一致（{len(generated.splitlines())} 行）")
            return 0
        diff = list(
            difflib.unified_diff(
                current.splitlines(),
                generated.splitlines(),
                fromfile=str(out),
                tofile="<regenerated>",
                lineterm="",
                n=1,
            )
        )
        print("\n".join(diff[:80]), file=sys.stderr)
        print(f"[gen] 漂移：生成物与契约不一致，请重新生成（{out}）", file=sys.stderr)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    init = out.parent / "__init__.py"
    if not init.exists():
        init.write_text("", encoding="utf-8")
    out.write_text(generated, encoding="utf-8", newline="\n")
    print(f"[gen] 已写入 {out}（{len(generated.splitlines())} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
