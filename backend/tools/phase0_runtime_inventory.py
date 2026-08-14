"""Build the Phase 0 static runtime inventory.

The inventory is deliberately conservative. ``dead`` means "not statically reachable
from the configured product, registered-route, or benchmark roots"; it is a review
candidate, not permission to delete the file. Dynamic imports and feature-flag activation
must be checked before changing a classification.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from collections import Counter, deque
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_APP = REPO_ROOT / "backend" / "app"
EXTENSION_SRC = REPO_ROOT / "extension" / "src"

BACKEND_LIVE_ROOTS = {
    "main.py",
    "api/routes/health.py",
    "api/routes/analyze.py",
    "api/routes/workflow.py",
    "api/routes/assist.py",
    "api/routes/intent.py",
    "api/routes/product.py",
    "mission_result/api.py",
}

STUB_PATTERNS = (
    re.compile(r"feature[- ]flagged stub", re.IGNORECASE),
    re.compile(r"interface[- ]only stubs?", re.IGNORECASE),
    re.compile(r"stub implementation", re.IGNORECASE),
    re.compile(r"all calls are no-ops", re.IGNORECASE),
)


def _source_files(root: Path, suffixes: set[str]) -> list[Path]:
    return sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.suffix in suffixes and "__pycache__" not in path.parts
    )


def _module_candidates(module: str, imported_names: Iterable[str] = ()) -> list[Path]:
    if not module.startswith("app"):
        return []
    rel_parts = module.split(".")[1:]
    base = BACKEND_APP.joinpath(*rel_parts)
    candidates = [base.with_suffix(".py"), base / "__init__.py"]
    candidates.extend(base / f"{name}.py" for name in imported_names)
    return [path for path in candidates if path.is_file()]


def _backend_dependencies(path: Path) -> set[Path]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    dependencies: set[Path] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                dependencies.update(_module_candidates(alias.name))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                current = path.relative_to(BACKEND_APP).with_suffix("").parts[:-1]
                keep = max(0, len(current) - node.level + 1)
                module = ".".join(("app", *current[:keep], *module.split(".")))
            dependencies.update(_module_candidates(module, (alias.name for alias in node.names)))
    return dependencies


IMPORT_RE = re.compile(
    r"(?:import\s+(?:[^'\"]+?\s+from\s+)?|require\s*\()\s*['\"]([^'\"]+)['\"]"
)


def _extension_dependencies(path: Path) -> set[Path]:
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return set()
    dependencies: set[Path] = set()
    for match in IMPORT_RE.finditer(source):
        target = match.group(1)
        if not target.startswith("."):
            continue
        base = (path.parent / target).resolve()
        for candidate in (
            base.with_suffix(".ts"),
            base.with_suffix(".tsx"),
            base / "index.ts",
            base / "index.tsx",
        ):
            if candidate.is_file() and EXTENSION_SRC in candidate.parents:
                dependencies.add(candidate)
    return dependencies


def _reachable(roots: Iterable[Path], dependency_map: dict[Path, set[Path]]) -> set[Path]:
    seen: set[Path] = set()
    queue = deque(path for path in roots if path.is_file())
    while queue:
        path = queue.popleft()
        if path in seen:
            continue
        seen.add(path)
        queue.extend(dependency_map.get(path, set()) - seen)
    return seen


def _is_explicit_stub(path: Path) -> bool:
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    return any(pattern.search(source) for pattern in STUB_PATTERNS)


def build_inventory() -> dict:
    backend_files = _source_files(BACKEND_APP, {".py"})
    extension_files = _source_files(EXTENSION_SRC, {".ts", ".tsx"})
    backend_graph = {path: _backend_dependencies(path) for path in backend_files}
    # ``main.py`` registers every API router. Traversing that registration import would
    # incorrectly label every optional/admin route as part of the core extension path.
    # Startup itself is live, but route reachability is classified from explicit roots.
    backend_graph[BACKEND_APP / "main.py"] = set()
    extension_graph = {path: _extension_dependencies(path) for path in extension_files}

    live_backend_roots = [BACKEND_APP / rel for rel in BACKEND_LIVE_ROOTS]
    shadow_backend_roots = [
        path for path in (BACKEND_APP / "api" / "routes").glob("*.py")
        if path.relative_to(BACKEND_APP).as_posix() not in BACKEND_LIVE_ROOTS
    ]
    live_backend = _reachable(live_backend_roots, backend_graph)
    shadow_backend = _reachable(shadow_backend_roots, backend_graph) - live_backend

    live_extension_roots = [
        EXTENSION_SRC / "background" / "service-worker.ts",
        EXTENSION_SRC / "sidepanel" / "index.tsx",
    ]
    live_extension = _reachable(live_extension_roots, extension_graph)

    test_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for root in (REPO_ROOT / "backend" / "tests", REPO_ROOT / "extension" / "tests")
        for path in root.rglob("*") if path.is_file()
    )

    entries: list[dict[str, str]] = []
    for path in [*backend_files, *extension_files]:
        rel = path.relative_to(REPO_ROOT).as_posix()
        if _is_explicit_stub(path):
            status, evidence = "stub", "explicit stub/no-op marker in source"
        elif path in live_backend or path in live_extension:
            status, evidence = "live", "statically reachable from a configured product entry root"
        elif path in shadow_backend:
            status, evidence = "shadow", "reachable from a registered API route not used by the core extension flow"
        elif path.name in test_text or path.stem in test_text:
            status, evidence = "test-only", "referenced by repository tests but not statically reachable from product roots"
        else:
            status, evidence = "dead", "no static reachability from configured product or registered-route roots"
        entries.append({"path": rel, "status": status, "evidence": evidence})

    entries.sort(key=lambda item: item["path"])
    counts = Counter(item["status"] for item in entries)
    return {
        "schema_version": "phase0.runtime-inventory.v1",
        "method": "conservative static import reachability",
        "status_semantics": {
            "live": "reachable from a current extension/backend product entry root",
            "shadow": "registered/reachable code outside the core extension request path",
            "test-only": "referenced by tests but not by configured product roots",
            "stub": "source explicitly identifies the implementation as a stub or no-op",
            "dead": "not statically reachable; review dynamic imports before deletion",
        },
        "counts": dict(sorted(counts.items())),
        "modules": entries,
    }


def render_markdown(inventory: dict) -> str:
    lines = [
        "# Phase 0 Runtime Inventory",
        "",
        "> Generated by `backend/tools/phase0_runtime_inventory.py`. Do not hand-edit.",
        "",
        "`dead` is a static-review candidate, not deletion authorization. Dynamic imports and feature flags must be checked.",
        "",
        "## Summary",
        "",
        "| Status | Files |",
        "|---|---:|",
    ]
    for status in ("live", "shadow", "test-only", "stub", "dead"):
        lines.append(f"| `{status}` | {inventory['counts'].get(status, 0)} |")
    lines.extend(["", "## Modules", "", "| Module | Status | Evidence |", "|---|---|---|"])
    for item in inventory["modules"]:
        lines.append(f"| `{item['path']}` | `{item['status']}` | {item['evidence']} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, help="write JSON inventory")
    parser.add_argument("--markdown", type=Path, help="write Markdown inventory")
    parser.add_argument("--check", action="store_true", help="fail when requested outputs are stale")
    args = parser.parse_args()
    inventory = build_inventory()
    outputs = []
    if args.json:
        outputs.append((args.json, json.dumps(inventory, indent=2) + "\n"))
    if args.markdown:
        outputs.append((args.markdown, render_markdown(inventory)))
    if not outputs:
        print(json.dumps(inventory["counts"], indent=2))
        return 0
    stale = [path for path, content in outputs if not path.exists() or path.read_text(encoding="utf-8") != content]
    if args.check:
        if stale:
            print("stale runtime inventory: " + ", ".join(str(path) for path in stale))
            return 1
        return 0
    for path, content in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
