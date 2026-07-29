from __future__ import annotations

import pytest

from app.core.config import settings
from app.feature_flags import FeatureFlagState, get_flag_state
from app.mission.blueprint import (
    BlueprintDependency,
    BlueprintEvidenceRequirement,
    BlueprintExpansionRule,
    BlueprintNode,
    BlueprintNodeKind,
    BlueprintNodeState,
    BlueprintValidationError,
    create_blueprint,
    deserialize_blueprint,
    serialize_blueprint,
    validate_blueprint,
)


def _node(node_id: str, objective: str = "Read source") -> BlueprintNode:
    return BlueprintNode(
        node_id=node_id,
        objective=objective,
        kind=BlueprintNodeKind.READING,
        state=BlueprintNodeState.PROPOSED,
        owner_capabilities=["knowledge_extraction"],
        evidence_requirements=[
            BlueprintEvidenceRequirement(
                requirement_id=f"ev_{node_id}",
                evidence_kind="page_read",
                subject=node_id,
            )
        ],
        expansion_rules=[
            BlueprintExpansionRule(
                rule_id=f"rule_{node_id}",
                capability="knowledge_extraction",
                intent_template="read_page",
            )
        ],
    )


def test_mission_blueprint_flag_defaults_to_off():
    assert settings.__class__.model_fields["mission_blueprint_v1"].default == "off"
    assert get_flag_state("MISSION_BLUEPRINT_V1") == FeatureFlagState.OFF


def test_create_blueprint_is_gated_by_feature_flag(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "off")

    with pytest.raises(BlueprintValidationError, match="disabled"):
        create_blueprint(
            mission_id="mission-1",
            objective="Research tools",
            nodes=[_node("read")],
        )


def test_create_validate_serialize_deserialize_blueprint(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")
    blueprint = create_blueprint(
        mission_id="mission-1",
        objective="Research AI browser tools",
        nodes=[
            _node("search", "Discover relevant sources"),
            _node("read", "Read selected source pages"),
        ],
        dependencies=[
            BlueprintDependency(
                dependency_id="dep_search_read",
                from_node_id="search",
                to_node_id="read",
            )
        ],
        success_criteria=["comparison_table_delivered"],
    )

    validate_blueprint(blueprint)
    payload = serialize_blueprint(blueprint)
    restored = deserialize_blueprint(payload)

    assert restored.blueprint_id == blueprint.blueprint_id
    assert restored.mission_id == "mission-1"
    assert [node.node_id for node in restored.nodes] == ["search", "read"]
    assert restored.dependencies[0].from_node_id == "search"
    assert restored.dependencies[0].to_node_id == "read"
    assert payload["schema_version"] == "mission_blueprint.v1"


def test_validation_rejects_duplicate_node_ids(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "active")

    with pytest.raises(BlueprintValidationError, match="unique"):
        create_blueprint(
            mission_id="mission-1",
            objective="Research tools",
            nodes=[_node("read"), _node("read")],
        )


def test_validation_rejects_unknown_dependency_node(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "active")

    with pytest.raises(BlueprintValidationError, match="unknown to_node_id"):
        create_blueprint(
            mission_id="mission-1",
            objective="Research tools",
            nodes=[_node("search")],
            dependencies=[
                BlueprintDependency(
                    dependency_id="dep_missing",
                    from_node_id="search",
                    to_node_id="read",
                )
            ],
        )


def test_validation_rejects_dependency_cycles(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "active")

    with pytest.raises(BlueprintValidationError, match="acyclic"):
        create_blueprint(
            mission_id="mission-1",
            objective="Research tools",
            nodes=[_node("a"), _node("b")],
            dependencies=[
                BlueprintDependency(dependency_id="a_to_b", from_node_id="a", to_node_id="b"),
                BlueprintDependency(dependency_id="b_to_a", from_node_id="b", to_node_id="a"),
            ],
        )


def test_blueprint_node_states_do_not_include_runtime_execution_states():
    runtime_states = {
        "QUEUED",
        "DISPATCHED",
        "EXECUTING",
        "WAITING_BROWSER",
        "COMPLETED",
        "FAILED",
        "BLOCKED",
    }

    assert runtime_states.isdisjoint({state.value.upper() for state in BlueprintNodeState})
