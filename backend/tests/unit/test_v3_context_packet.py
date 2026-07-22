from __future__ import annotations

import json

from app.context_packet import ContextPacketBuilder, PlannerV2Adapter
from app.context_packet.budget import ContextPacketBudget
from app.context_packet.models import PlannerPacket
from app.feature_flags import is_shadow_or_active
from app.semantic_page.builder import SemanticPageGraphBuilder
from tests.unit.test_v3_semantic_page_graph import sample_page


def _packet(budget: ContextPacketBudget | None = None) -> PlannerPacket:
    page = sample_page()
    graph = SemanticPageGraphBuilder().build(page)
    packet, _build_ms = ContextPacketBuilder(budget).build(
        run_id="context-run",
        task="Compare browser automation repositories",
        page_context=page,
        semantic_graph=graph,
        prior_steps=[
            {
                "action_type": "click",
                "description": "Opened first result",
                "execution_result": "success",
            }
        ],
        supplemental_context="Mission Status: collecting\nWorkspace: first repository opened",
        verified_facts={"repo": "lightpanda-io/browser"},
        compressed_context={
            "active_goal": "Compare browser automation repositories",
            "verified_facts": {"repo": "lightpanda-io/browser"},
            "recent_actions": [{"description": "Opened first result"}],
            "important_failures": [],
            "task_constraints": ["Use visible evidence"],
        },
    )
    return packet


def test_context_packet_generation_is_deterministic_byte_for_byte():
    assert _packet().to_stable_json() == _packet().to_stable_json()


def test_context_packet_semantic_projection_is_planner_focused():
    packet = _packet()
    semantic = packet.page_context["semantic"]

    assert semantic["graph_id"].startswith("graph.")
    assert "nodes" not in semantic
    assert "edges" not in semantic
    assert [target["semantic_role"] for target in semantic["semantic_targets"]] == [
        "download_file",
        "navigate_link",
        "search_field",
    ]
    assert semantic["facts"][0]["label"] in {"lang", "visible_content"}


def test_context_packet_budget_trims_deterministically():
    packet = _packet(ContextPacketBudget(max_targets=1, max_facts=1, max_controls=1, max_entities=1))
    semantic = packet.page_context["semantic"]

    assert len(semantic["semantic_targets"]) == 1
    assert len(semantic["facts"]) == 1
    assert len(semantic["controls"]) == 1
    assert len(semantic["entities"]) == 1
    assert packet.budget_metadata.trimmed_counts["targets"] == 2
    assert packet.budget_metadata.trimmed_counts["facts"] == 2


def test_context_packet_serialization_round_trips_stably():
    packet = _packet()
    serialized = packet.to_stable_json()
    loaded = PlannerPacket.model_validate(json.loads(serialized))

    assert loaded.to_stable_json() == serialized
    assert loaded.schema_version == "planner_packet.v1"
    assert loaded.output_contract == "planner_contract_v2"


def test_planner_v2_adapter_preserves_legacy_inputs():
    packet = _packet()
    page = sample_page()
    prior_steps = [{"action_type": "click"}]
    compressed_context = {"active_goal": "goal"}

    legacy = PlannerV2Adapter().to_legacy_inputs(
        packet=packet,
        task="goal",
        page_context=page,
        prior_steps=prior_steps,
        supplemental_context="legacy supplemental",
        verified_state={"fact": "value"},
        compressed_context=compressed_context,
    )

    assert legacy["task"] == "goal"
    assert legacy["page_context"] is page
    assert legacy["prior_steps"] is prior_steps
    assert legacy["compressed_context"] is compressed_context
    assert legacy["output_contract"] == "planner_contract_v2"


def test_context_packet_feature_flag_default_and_off(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "v3_context_packet", "shadow")
    assert is_shadow_or_active("V3_CONTEXT_PACKET") is True

    monkeypatch.setattr(settings, "v3_context_packet", "off")
    assert is_shadow_or_active("V3_CONTEXT_PACKET") is False


def test_context_packet_performance_budget_for_typical_observation():
    page = sample_page()
    graph = SemanticPageGraphBuilder().build(page)
    packet, build_ms = ContextPacketBuilder().build(
        run_id="perf-run",
        task="Compare browser automation repositories",
        page_context=page,
        semantic_graph=graph,
        prior_steps=[],
        supplemental_context="",
        verified_facts={},
        compressed_context={"active_goal": "Compare browser automation repositories"},
    )

    assert build_ms < 50
    assert packet.budget_metadata.packet_chars < 12000
