import json

from tools.phase0_runtime_inventory import BACKEND_APP, EXTENSION_SRC, build_inventory, render_markdown


def test_runtime_inventory_covers_every_source_module_once():
    inventory = build_inventory()
    actual = {
        path.resolve()
        for root, suffixes in ((BACKEND_APP, {".py"}), (EXTENSION_SRC, {".ts", ".tsx"}))
        for path in root.rglob("*")
        if path.is_file() and path.suffix in suffixes and "__pycache__" not in path.parts
    }
    repo_root = BACKEND_APP.parents[1]
    recorded = {(repo_root / item["path"]).resolve() for item in inventory["modules"]}
    assert recorded == actual


def test_runtime_inventory_uses_only_phase0_statuses():
    inventory = build_inventory()
    statuses = {item["status"] for item in inventory["modules"]}
    assert statuses <= {"live", "shadow", "test-only", "stub", "dead"}
    assert {"live", "shadow", "stub", "dead"} <= statuses


def test_core_and_registered_non_core_routes_are_distinguished():
    inventory = build_inventory()
    status_by_path = {item["path"]: item["status"] for item in inventory["modules"]}
    assert status_by_path["backend/app/api/routes/analyze.py"] == "live"
    assert status_by_path["backend/app/api/routes/trust.py"] == "shadow"
    assert status_by_path["extension/src/background/service-worker.ts"] == "live"


def test_explicit_persistence_stub_is_not_reported_live():
    inventory = build_inventory()
    status_by_path = {item["path"]: item["status"] for item in inventory["modules"]}
    assert status_by_path["backend/app/approvals/persistence.py"] == "stub"


def test_committed_runtime_inventory_is_current():
    inventory = build_inventory()
    repo_root = BACKEND_APP.parents[1]
    json_path = repo_root / "docs" / "phase0" / "runtime-inventory.json"
    markdown_path = repo_root / "docs" / "phase0" / "runtime-inventory.md"
    assert json_path.read_text(encoding="utf-8") == json.dumps(inventory, indent=2) + "\n"
    assert markdown_path.read_text(encoding="utf-8") == render_markdown(inventory)
