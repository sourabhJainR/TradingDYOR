"""Guard production paths from importing cross-repository test runtimes."""
from __future__ import annotations

import ast
import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_MODULES = ("portable", "ardisa", "ardisa_core", "aifocus", "aifocus_core")
FORBIDDEN_PACKAGES = {"auren", "ardisa", "ardisa-core", "aifocus", "aifocus-core"}
PRODUCTION_ROOTS = ("tradingdyor", "agents/src", "scripts", "web")


def forbidden_module(name: str) -> bool:
    return any(name == prefix or name.startswith(prefix + ".") for prefix in FORBIDDEN_MODULES)


def test_production_python_paths_do_not_import_cross_repository_runtime_code():
    violations = []
    for root_name in PRODUCTION_ROOTS:
        root = ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as error:
                violations.append(f"{path}: syntax error: {error}")
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [item.name for item in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                else:
                    continue
                for name in names:
                    if forbidden_module(name):
                        violations.append(f"{path}: import {name}")
    assert not violations, "\n".join(violations)


def test_production_node_paths_do_not_import_cross_repository_runtime_code():
    pattern = re.compile(
        r"(?:from\s+|require\s*\(|import\s+)['\"](?:portable|ardisa|aifocus|aifocus_core|ardisa_core)(?:/|\.)",
        re.IGNORECASE,
    )
    violations = []
    for root_name in ("agents/src", "web"):
        root = ROOT / root_name
        if not root.exists():
            continue
        for suffix in ("*.js", "*.mjs", "*.cjs"):
            for path in root.rglob(suffix):
                if pattern.search(path.read_text(encoding="utf-8", errors="replace")):
                    violations.append(str(path))
    assert not violations, "cross-repository runtime import detected: " + ", ".join(violations)


def test_production_dependency_manifests_do_not_depend_on_auren_or_ardisa():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = list(pyproject.get("project", {}).get("dependencies", []))
    for group in pyproject.get("project", {}).get("optional-dependencies", {}).values():
        dependencies.extend(group)
    names = {re.split(r"[<>=!~; ]", item, maxsplit=1)[0].lower().replace("_", "-") for item in dependencies}
    forbidden = sorted(names & FORBIDDEN_PACKAGES)
    assert not forbidden, f"forbidden Python dependencies: {forbidden}"

    package_path = ROOT / "agents" / "package.json"
    if package_path.exists():
        package = json.loads(package_path.read_text(encoding="utf-8"))
        node_dependencies = set(package.get("dependencies", {})) | set(package.get("devDependencies", {}))
        forbidden = sorted({name.lower() for name in node_dependencies} & FORBIDDEN_PACKAGES)
        assert not forbidden, f"forbidden Node dependencies: {forbidden}"
