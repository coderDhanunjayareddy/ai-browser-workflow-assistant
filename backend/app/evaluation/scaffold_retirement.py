from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_retirement_register(inventory_path: Path) -> dict[str, Any]:
    """Archive unreachable scaffolding from production claims without deleting source.

    Static reachability is enough to quarantine a module from production claims,
    but physical deletion remains blocked until dynamic-import and paired E2E
    evidence are attached to a future register revision.
    """
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    rows = []
    for module in inventory.get("modules", []):
        if module.get("status") not in {"dead", "stub"}:
            continue
        rows.append({
            "path": module["path"],
            "inventory_status": module["status"],
            "production_claim": "archived",
            "source_action": "retain_quarantined",
            "reason": module.get("evidence", "not reachable from production roots"),
            "physical_removal_gate": {
                "dynamic_import_audit": False,
                "paired_e2e_samples": 0,
                "non_positive_completion_delta": None,
                "approved": False,
            },
        })
    return {
        "schema_version": "production_evidence.scaffold_retirement.v1",
        "source_inventory": "docs/phase0/runtime-inventory.json",
        "policy": "archive dead/stub modules from production claims; never auto-delete source",
        "archived_from_production_count": len(rows),
        "entries": rows,
    }
