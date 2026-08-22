import json
import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
AUTHORITY_MAP = REPOSITORY_ROOT / "docs" / "architecture" / "generic-authority-map.json"


def _load_map() -> dict:
    return json.loads(AUTHORITY_MAP.read_text(encoding="utf-8"))


def test_every_runtime_stage_has_one_explicit_current_and_target_authority():
    authority_map = _load_map()
    stages = authority_map["stages"]
    names = [stage["stage"] for stage in stages]
    assert len(names) == len(set(names))
    assert all(isinstance(stage["current_authority"], str) for stage in stages)
    assert all(isinstance(stage["target_authority"], str) for stage in stages)
    assert all(stage["migration_state"] for stage in stages)


def test_every_declared_authority_and_strategy_exists_in_the_repository():
    for stage in _load_map()["stages"]:
        declared = [stage["current_authority"], stage["target_authority"]]
        declared.extend(stage.get("competing_components", []))
        declared.extend(stage.get("leaf_strategies", []))
        missing = [path for path in declared if not (REPOSITORY_ROOT / path).is_file()]
        assert not missing, f"Authority map contains missing source paths: {missing}"


def test_only_one_component_is_allowed_to_be_the_browser_dispatch_gateway():
    stages = _load_map()["stages"]
    gateways = [stage for stage in stages if stage["stage"] == "browser_dispatch_gateway"]
    assert len(gateways) == 1
    gateway = gateways[0]
    assert gateway["current_authority"] == gateway["target_authority"]
    assert gateway["entrypoint"] == "handleExecuteAction"


def test_competing_components_cannot_also_be_authoritative_for_the_same_stage():
    for stage in _load_map()["stages"]:
        competitors = set(stage.get("competing_components", []))
        assert stage["current_authority"] not in competitors
        assert stage["target_authority"] not in competitors


def test_active_core_boundaries_contain_no_named_application_or_service_literals():
    guarded_files = [
        "backend/app/orchestrator/workflow_orchestrator.py",
        "backend/app/execution_orchestrator/engine.py",
        "extension/src/content/exact_target_verification.ts",
        "extension/src/execution/exact_open_completion.ts",
    ]
    forbidden = re.compile(
        r"\b(whatsapp|gmail|youtube|linkedin|instagram|amazon|makemytrip)\b",
        flags=re.IGNORECASE,
    )
    violations = {}
    for relative_path in guarded_files:
        text = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
        matches = sorted({match.group(0).casefold() for match in forbidden.finditer(text)})
        if matches:
            violations[relative_path] = matches
    assert not violations, f"Named application literals must remain in registry/adapter/test paths: {violations}"
