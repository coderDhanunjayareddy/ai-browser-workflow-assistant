from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.evaluation.production import (
    CapabilityGate,
    DisposableAccount,
    GateThresholds,
    LiveEvaluationEvidence,
    ProductionEvidenceStore,
)
from app.evaluation.red_team import run_live_policy_red_team
from app.evaluation.scaffold_retirement import build_retirement_register
from app.main import app


def account(**updates) -> DisposableAccount:
    values = {
        "alias": "shopper-a",
        "provider": "controlled-store",
        "allowed_origins": ["https://shop.fixture.example/account"],
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    values.update(updates)
    return DisposableAccount(**values)


def evidence(leased: DisposableAccount, **updates) -> LiveEvaluationEvidence:
    values = {
        "task_id": "checkout-dry-run",
        "capability": "cdp_input",
        "account_id": leased.account_id,
        "lease_id": leased.lease_id,
        "origin": "https://shop.fixture.example/checkout",
        "success": True,
        "completion_validated": True,
        "confirmation_required": True,
        "confirmation_shown": True,
        "trace_refs": ["trace://checkout-dry-run/1"],
    }
    values.update(updates)
    return LiveEvaluationEvidence(**values)


def test_disposable_account_registry_rejects_secrets_and_wrong_origin(tmp_path: Path):
    with pytest.raises(ValueError, match="never credentials"):
        account(metadata={"password": "must-not-be-stored"})

    store = ProductionEvidenceStore(tmp_path / "evidence.json")
    registered = store.register_account(account())
    leased = store.lease_account(registered.account_id)
    with pytest.raises(ValueError, match="outside"):
        store.record(evidence(leased, origin="https://attacker.example"))


def test_account_lease_prevents_account_confusion_and_is_durable(tmp_path: Path):
    path = tmp_path / "evidence.json"
    store = ProductionEvidenceStore(path)
    first = store.lease_account(store.register_account(account(alias="first")).account_id)
    second = store.lease_account(store.register_account(account(alias="second")).account_id)
    confused = evidence(first, lease_id=second.lease_id)
    with pytest.raises(ValueError, match="active lease"):
        store.record(confused)
    store.record(evidence(first))
    assert ProductionEvidenceStore(path).summary()["evidence_count"] == 1


def test_red_team_uses_live_gate_and_stops_all_four_attack_classes():
    report = run_live_policy_red_team()
    assert report["engine"] == "app.policy.live_engine.LivePolicyEngine"
    assert report["exit_gate_passed"] is True
    assert report["critical_confirmation_recall"] == 1.0
    assert {case["category"] for case in report["cases"]} == {
        "prompt_injection", "cross_origin_leakage", "account_confusion", "confirmation_bypass",
    }


def test_capability_promotions_are_independent_and_evidence_gated(tmp_path: Path):
    store = ProductionEvidenceStore(tmp_path / "evidence.json")
    leased = store.lease_account(store.register_account(account()).account_id)
    thresholds = GateThresholds(min_samples=2, min_success_rate=1, min_completion_validation_rate=1)
    store.configure_gate(CapabilityGate(capability="cdp_input", stage="shadow", thresholds=thresholds))
    store.configure_gate(CapabilityGate(capability="isolated_research", stage="off", thresholds=thresholds))

    assert store.evaluate_gate("cdp_input", "canary").allowed is False
    store.record(evidence(leased, task_id="one"))
    store.record(evidence(leased, task_id="two"))
    promoted = store.evaluate_gate("cdp_input", "canary")
    assert promoted.allowed is True
    assert promoted.resulting_stage == "canary"
    assert store.summary()["capabilities"]["isolated_research"]["stage"] == "off"
    restored = ProductionEvidenceStore(tmp_path / "evidence.json")
    assert len(restored.summary()["recent_gate_decisions"]) == 2


def test_red_team_run_history_is_durable(tmp_path: Path):
    path = tmp_path / "evidence.json"
    store = ProductionEvidenceStore(path)
    recorded = store.record_red_team_run(run_live_policy_red_team())
    summary = ProductionEvidenceStore(path).summary()
    assert summary["red_team_run_count"] == 1
    assert summary["latest_red_team_run"]["run_id"] == recorded["run_id"]


def test_critical_failure_forces_rollback(tmp_path: Path):
    store = ProductionEvidenceStore(tmp_path / "evidence.json")
    leased = store.lease_account(store.register_account(account()).account_id)
    store.configure_gate(CapabilityGate(
        capability="cdp_input", stage="canary", thresholds=GateThresholds(min_samples=1),
    ))
    store.record(evidence(leased, success=False, completion_validated=False, critical_failure=True))
    decision = store.evaluate_gate("cdp_input", "active")
    assert decision.allowed is False
    assert decision.resulting_stage == "rollback"


def test_scaffolding_is_archived_from_claims_but_never_auto_deleted():
    inventory = Path(__file__).resolve().parents[3] / "docs" / "phase0" / "runtime-inventory.json"
    report = build_retirement_register(inventory)
    assert report["archived_from_production_count"] > 0
    assert all(row["production_claim"] == "archived" for row in report["entries"])
    assert all(row["source_action"] == "retain_quarantined" for row in report["entries"])
    assert not any(row["physical_removal_gate"]["approved"] for row in report["entries"])


def test_phase5_api_exposes_red_team_and_retirement_evidence(tmp_path: Path, monkeypatch):
    from app.api.routes import production_evidence as route_module

    monkeypatch.setattr(route_module, "production_evidence_store", ProductionEvidenceStore(tmp_path / "api-evidence.json"))
    client = TestClient(app)
    red_team = client.post("/production-evidence/red-team/run")
    retirement = client.get("/production-evidence/scaffolding/retirement-register")
    assert red_team.status_code == 200
    assert red_team.json()["exit_gate_passed"] is True
    assert retirement.status_code == 200
    assert retirement.json()["archived_from_production_count"] > 0
