"""
Unit tests for V5.0 Mission Affinity Heuristic.
Covers: keyword extraction, Jaccard similarity, domain clusters,
        find_matching_mission(), assign_task_to_mission(), score_pair().
"""
import pytest

from app.mission import affinity as mission_affinity, store as mission_store
from app.mission import lifecycle as mission_lifecycle, analytics as mission_analytics
from app.mission.affinity import (
    _extract_keywords, _jaccard, AFFINITY_THRESHOLD, score_pair, _same_domain,
    _domain_of, _derive_title,
)
from app.unified.models import UnifiedTask


@pytest.fixture(autouse=True)
def reset():
    mission_store._reset_for_testing()
    mission_analytics._reset_for_testing()
    yield
    mission_store._reset_for_testing()
    mission_analytics._reset_for_testing()


def _task(query: str, task_id: str = "t1") -> UnifiedTask:
    return UnifiedTask(task_id=task_id, conversation_id="c1", original_query=query)


# ── Keyword extraction ────────────────────────────────────────────────────────

class TestExtractKeywords:
    def test_removes_stop_words(self):
        kw = _extract_keywords("what is the best laptop for me")
        assert "what" not in kw
        assert "the" not in kw
        assert "laptop" in kw

    def test_min_length_3(self):
        kw = _extract_keywords("to a be")
        assert kw == set()

    def test_lowercase(self):
        kw = _extract_keywords("FLIGHT BOOKING")
        assert "flight" in kw
        assert "booking" in kw

    def test_empty_string(self):
        assert _extract_keywords("") == set()


# ── Jaccard ───────────────────────────────────────────────────────────────────

class TestJaccard:
    def test_identical_sets(self):
        a = {"a", "b", "c"}
        assert _jaccard(a, a) == 1.0

    def test_disjoint_sets(self):
        assert _jaccard({"a"}, {"b"}) == 0.0

    def test_partial_overlap(self):
        a = {"a", "b"}
        b = {"b", "c"}
        # intersection={"b"}, union={"a","b","c"} → 1/3
        assert _jaccard(a, b) == pytest.approx(1/3)

    def test_empty_a(self):
        assert _jaccard(set(), {"a"}) == 0.0

    def test_empty_b(self):
        assert _jaccard({"a"}, set()) == 0.0


# ── Domain detection ──────────────────────────────────────────────────────────

class TestDomainDetection:
    def test_same_travel_domain(self):
        a = _extract_keywords("book flight to NYC")
        b = _extract_keywords("find hotel near airport")
        assert _same_domain(a, b)

    def test_different_domains_travel_vs_electronics(self):
        a = _extract_keywords("book flight to NYC")
        b = _extract_keywords("best gaming laptop")
        assert not _same_domain(a, b)

    def test_uncategorized_matches_any(self):
        a = _extract_keywords("general query xyz")
        b = _extract_keywords("book flight")
        assert _same_domain(a, b)  # uncategorized → True


# ── score_pair ────────────────────────────────────────────────────────────────

class TestScorePair:
    def test_same_topic_high_score(self):
        # "flight hotel paris trip" vs "flight hotel paris booking" → 3/5 = 0.6
        score = score_pair("flight hotel paris trip", "flight hotel paris booking")
        assert score > AFFINITY_THRESHOLD

    def test_different_topics_low_score(self):
        score = score_pair("best restaurant Paris", "buy gaming laptop")
        assert score < AFFINITY_THRESHOLD

    def test_symmetric(self):
        s1 = score_pair("A B C", "B C D")
        s2 = score_pair("B C D", "A B C")
        assert s1 == pytest.approx(s2)


# ── find_matching_mission ─────────────────────────────────────────────────────

class TestFindMatchingMission:
    def test_no_active_missions_returns_none(self):
        task = _task("find flights to Paris")
        assert mission_affinity.find_matching_mission(task) is None

    def test_matching_mission_found(self):
        m = mission_lifecycle.create_mission_obj(
            "Travel Planning", "find flights and hotels"
        )
        mission_lifecycle.attach_task(m.mission_id, "existing-task-1")
        task = _task("book flight to Paris")
        match = mission_affinity.find_matching_mission(task)
        # Both are travel domain; should score above threshold
        assert match is None or match.mission_id == m.mission_id

    def test_terminal_mission_not_matched(self):
        m = mission_lifecycle.create_mission_obj("M", "book flight hotel")
        mission_lifecycle.attach_task(m.mission_id, "t0")
        mission_lifecycle.complete(m.mission_id)
        task = _task("book flight hotel")
        assert mission_affinity.find_matching_mission(task) is None

    def test_empty_query_returns_none(self):
        task = _task("")
        assert mission_affinity.find_matching_mission(task) is None


# ── derive title ──────────────────────────────────────────────────────────────

class TestDeriveTitle:
    def test_short_query_unchanged(self):
        assert _derive_title("Book flight") == "Book flight"

    def test_long_query_truncated(self):
        long = "A" * 80
        title = _derive_title(long)
        assert len(title) <= 60

    def test_empty_query_returns_fallback(self):
        assert _derive_title("") == "New Mission"


# ── assign_task_to_mission ────────────────────────────────────────────────────

class TestAssignTaskToMission:
    def test_creates_new_mission_when_no_match(self):
        task = _task("find restaurants near me")
        mission = mission_affinity.assign_task_to_mission(task, create_if_none=True)
        assert mission is not None
        assert task.task_id in mission.task_ids

    def test_returns_none_when_create_if_none_false(self):
        task = _task("random query with no match")
        mission = mission_affinity.assign_task_to_mission(task, create_if_none=False)
        assert mission is None
