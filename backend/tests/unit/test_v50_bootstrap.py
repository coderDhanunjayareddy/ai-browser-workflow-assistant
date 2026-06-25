"""
Unit tests for V5.0 MissionBootstrap.
Covers: enrich_task_bootstrap(), enrich_handoff_payload(),
        entity merging order, enriched_facts structure, latency.
"""
import pytest

from app.mission import bootstrap as mission_bootstrap
from app.mission import store as mission_store
from app.mission import lifecycle as mission_lifecycle, analytics as mission_analytics
from app.mission.models import create_mission
from app.unified import store as task_store
from app.unified.models import UnifiedTask, TaskState


@pytest.fixture(autouse=True)
def reset():
    mission_store._reset_for_testing()
    mission_analytics._reset_for_testing()
    yield
    mission_store._reset_for_testing()
    mission_analytics._reset_for_testing()


def _put_task(task_id: str, query: str = "test", entities: dict = None) -> UnifiedTask:
    t = UnifiedTask(task_id=task_id, conversation_id="c1", original_query=query)
    if entities:
        t.entities = entities
    task_store.put(t)
    return t


class TestEnrichTaskBootstrap:
    def test_returns_none_for_unknown_mission(self):
        _put_task("t1")
        result = mission_bootstrap.enrich_task_bootstrap("t1", "no-such-mission")
        assert result is None

    def test_returns_none_for_unknown_task(self):
        m = mission_lifecycle.create_mission_obj("M")
        result = mission_bootstrap.enrich_task_bootstrap("ghost-task", m.mission_id)
        assert result is None

    def test_returns_result_for_valid_mission_and_task(self):
        m = mission_lifecycle.create_mission_obj("M", "find flights")
        t = _put_task("t1", "book flight")
        mission_lifecycle.attach_task(m.mission_id, t.task_id)
        result = mission_bootstrap.enrich_task_bootstrap(t.task_id, m.mission_id)
        assert result is not None
        assert result.mission_id == m.mission_id
        assert result.task_id == t.task_id

    def test_mission_entity_merging(self):
        m = mission_lifecycle.create_mission_obj("M")
        t_prev = _put_task("t_prev", entities={"city": "London"})
        mission_lifecycle.attach_task(m.mission_id, t_prev.task_id)
        t_new = _put_task("t_new", entities={"airport": "Heathrow"})
        mission_lifecycle.attach_task(m.mission_id, t_new.task_id)
        result = mission_bootstrap.enrich_task_bootstrap(t_new.task_id, m.mission_id)
        assert "city" in result.merged_entities
        assert "airport" in result.merged_entities

    def test_enriched_facts_contains_mission_fields(self):
        m = mission_lifecycle.create_mission_obj("Plan Trip", "travel mission")
        t = _put_task("t1")
        mission_lifecycle.attach_task(m.mission_id, t.task_id)
        result = mission_bootstrap.enrich_task_bootstrap(t.task_id, m.mission_id)
        assert result.enriched_facts["mission_id"] == m.mission_id
        assert result.enriched_facts["mission_title"] == "Plan Trip"

    def test_latency_ms_non_negative(self):
        m = mission_lifecycle.create_mission_obj("M")
        t = _put_task("t1")
        mission_lifecycle.attach_task(m.mission_id, t.task_id)
        result = mission_bootstrap.enrich_task_bootstrap(t.task_id, m.mission_id)
        assert result.latency_ms >= 0

    def test_mission_entity_count(self):
        m = mission_lifecycle.create_mission_obj("M")
        t = _put_task("t1", entities={"k1": "v1", "k2": "v2"})
        mission_lifecycle.attach_task(m.mission_id, t.task_id)
        result = mission_bootstrap.enrich_task_bootstrap(t.task_id, m.mission_id)
        assert result.mission_entity_count == 2


class TestEnrichHandoffPayload:
    def test_returns_unchanged_for_unknown_mission(self):
        payload = {"key": "value"}
        result = mission_bootstrap.enrich_handoff_payload(payload, "ghost")
        assert result == payload

    def test_adds_mission_id_and_title(self):
        m = mission_lifecycle.create_mission_obj("My Mission")
        payload = {}
        result = mission_bootstrap.enrich_handoff_payload(payload, m.mission_id)
        assert result["mission_id"] == m.mission_id
        assert result["mission_title"] == "My Mission"

    def test_does_not_override_existing_mission_id(self):
        m = mission_lifecycle.create_mission_obj("M")
        payload = {"mission_id": "override-me-not"}
        result = mission_bootstrap.enrich_handoff_payload(payload, m.mission_id)
        # setdefault means it won't override
        assert result["mission_id"] == "override-me-not"

    def test_merges_pre_filled_facts(self):
        m = mission_lifecycle.create_mission_obj("M")
        t = _put_task("t1", entities={"mission_entity": "mval"})
        mission_lifecycle.attach_task(m.mission_id, t.task_id)
        payload = {"pre_filled_facts": {"task_entity": "tval"}}
        result = mission_bootstrap.enrich_handoff_payload(payload, m.mission_id)
        facts = result["pre_filled_facts"]
        assert "task_entity" in facts
        assert "mission_entity" in facts
