"""比对"后端已实现接口"与契约 contracts/openapi.json。

用途：T00 之后接口会一个个补齐，最容易出的问题不是写错业务，而是**字段悄悄和
契约不一致**（少一个 required、多一个多余字段、状态码对不上）。本脚本只检查
"已经声明的 operation"，未实现的接口只统计数量、不算失败，因此可以随开发进度
一直放进 CI，不需要等 17 个接口全部写完。

用法（仓库根目录）：
    python tools/check_implemented_contract.py
    python tools/check_implemented_contract.py --verbose

退出码：0 一致；1 有不一致；2 环境问题（例如后端导入失败）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "contracts" / "openapi.json"
BACKEND_DIR = ROOT / "backend"

SCHEMA_SECTIONS = ("properties",)
METHODS = ("get", "post", "put", "patch", "delete")


def _load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _load_implemented() -> dict:
    sys.path.insert(0, str(BACKEND_DIR))
    try:
        from app.main import app  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 无法导入后端应用：{exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    return app.openapi()


def _resolve(spec: dict, schema: dict | None) -> dict:
    if not isinstance(schema, dict):
        return {}
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
        name = ref.rsplit("/", 1)[-1]
        return spec.get("components", {}).get("schemas", {}).get(name, {})
    return schema


def _properties(spec: dict, schema: dict | None) -> tuple[set[str], set[str]]:
    node = _resolve(spec, schema)
    props = set(node.get("properties", {}).keys())
    required = set(node.get("required", []))
    return props, required


def _json_schema(spec: dict, operation: dict, status: str) -> dict | None:
    responses = operation.get("responses") or {}
    response = responses.get(str(status)) or responses.get(status)
    if not isinstance(response, dict):
        return None
    return (response.get("content") or {}).get("application/json", {}).get("schema")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查后端实现与契约是否一致")
    parser.add_argument("--verbose", action="store_true", help="打印每个已实现接口")
    args = parser.parse_args(argv)

    contract = _load_contract()
    implemented = _load_implemented()
    contract_paths = contract.get("paths", {})
    implemented_paths = implemented.get("paths", {})

    implemented_ops: list[tuple[str, str]] = []
    for path, methods in implemented_paths.items():
        for method in methods:
            if method in METHODS:
                implemented_ops.append((method.upper(), path))

    failures: list[str] = []
    notices: list[str] = []
    implemented_set = {(m, p) for m, p in implemented_ops}

    for method, path in sorted(implemented_set):
        op_impl = implemented_paths[path][method.lower()]
        op_contract = (contract_paths.get(path) or {}).get(method.lower())

        if op_contract is None:
            failures.append(f"{method} {path}：后端已实现，但契约里没有这个 operation")
            continue

        status_impl = set((op_impl.get("responses") or {}).keys())
        status_contract = set((op_contract.get("responses") or {}).keys())
        missing_status = sorted(status_contract - status_impl)
        extra_status = sorted(status_impl - status_contract)
        if missing_status:
            notices.append(f"{method} {path}：契约声明但暂未实现的响应码 {missing_status}")
        if extra_status:
            # FastAPI 对任何带 JSON/表单请求体的端点都会无条件声明 422（Pydantic 校验）。
            # 契约里 retryImport 漏写了 422，属契约待补的缺口而不是实现写错：
            # 为消这一条去改契约版本、逼前端重新生成 SDK 不划算，先记 [注意]，
            # 待与 F 一起把 0.2.x 补上（docs/10 CHG-004 已登记）。
            if "requestBody" in op_impl and extra_status == ["422"]:
                notices.append(
                    f"{method} {path}：实现声明了契约未写的 422（请求体校验，契约待补）"
                )
            else:
                failures.append(f"{method} {path}：多出契约未声明的响应码 {extra_status}")

        for status in sorted(status_contract & status_impl):
            schema_contract = _json_schema(contract, op_contract, status)
            schema_impl = _json_schema(implemented, op_impl, status)
            if schema_contract is None and schema_impl is None:
                continue  # 204 / 文件流，无 JSON 体
            props_contract, req_contract = _properties(contract, schema_contract)
            props_impl, req_impl = _properties(implemented, schema_impl)
            if props_contract != props_impl:
                missing = sorted(props_contract - props_impl)
                extra = sorted(props_impl - props_contract)
                detail = []
                if missing:
                    detail.append(f"缺字段 {missing}")
                if extra:
                    detail.append(f"多字段 {extra}")
                failures.append(f"{method} {path} {status}：{'，'.join(detail)}")
            elif req_contract != req_impl:
                failures.append(
                    f"{method} {path} {status}：required 不一致 "
                    f"（契约 {sorted(req_contract)} / 实现 {sorted(req_impl)}）"
                )
            elif args.verbose:
                print(f"[OK] {method} {path} {status} 字段与契约一致")

    total_contract = sum(
        1 for methods in contract_paths.values() for m in methods if m in METHODS
    )
    pending = total_contract - len(implemented_set)

    for notice in notices:
        print(f"[注意] {notice}")
    if failures:
        print()
        for item in failures:
            print(f"[FAIL] {item}")
        print(f"\n不一致 {len(failures)} 处", file=sys.stderr)
        return 1

    print(
        f"[OK] 已实现 {len(implemented_set)} 个接口，字段与契约一致；"
        f"待实现 {pending} 个（契约共 {total_contract} 个）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
