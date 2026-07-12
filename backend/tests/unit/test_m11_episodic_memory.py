"""
M1.1 — Episodic memory restoration.

Covers the two changed files:
  - app/context_compression/state_summarizer.py (StateSummarizer.summarize)
  - app/context_compression/compressor.py (ContextCompressor.compress)

Scope: restore the previously-discarded record of successful prior actions (with selector)
into the compressed context, as `recent_actions`. No other M1 milestone is exercised here.
"""
from unittest.mock import MagicMock

from app.context_compression.state_summarizer import StateSummarizer, _infer_page_changed
from app.context_compression.compressor import ContextCompressor
from app.schemas.request import PriorStep


def _page(elements=None):
    pc = MagicMock()
    pc.interactive_elements = elements or []
    pc.content_blocks = []
    pc.visible_text = ""
    return pc


def _page_with_content(*, text: str, selector: str = "section", visible_text: str = ""):
    pc = _page()
    pc.content_blocks = [{"selector": selector, "text": text}]
    pc.visible_text = visible_text
    return pc


# ── StateSummarizer ──────────────────────────────────────────────────────────

def test_successful_step_preserves_selector_action_and_value():
    step = PriorStep(action_type="click", description="click the '2' pagination link",
                     target_selector="#p2", value=None, execution_result="success")
    out = StateSummarizer().summarize(active_goal="goal", verified_facts={}, prior_steps=[step])
    assert len(out["completed_nodes"]) == 1
    entry = out["completed_nodes"][0]
    assert entry["selector"] == "#p2"
    assert entry["action_type"] == "click"
    assert entry["description"] == "click the '2' pagination link"
    assert entry["value"] is None


def test_fill_step_preserves_typed_value():
    step = PriorStep(action_type="fill", description="fill username", target_selector="#u",
                     value="tester", execution_result="success")
    out = StateSummarizer().summarize(active_goal="g", verified_facts={}, prior_steps=[step])
    entry = out["completed_nodes"][0]
    assert entry["selector"] == "#u"
    assert entry["value"] == "tester"


def test_failed_step_still_routes_to_important_failures_unchanged():
    step = PriorStep(action_type="click", description="click submit", target_selector="#go",
                     execution_result="Click target not found: #go")
    out = StateSummarizer().summarize(active_goal="g", verified_facts={}, prior_steps=[step])
    assert out["completed_nodes"] == []
    assert out["important_failures"] == [
        {"step": "click submit", "error": "Click target not found: #go"}
    ]


def test_multiple_steps_preserve_order():
    steps = [
        PriorStep(action_type="fill", description="fill username", target_selector="#u",
                  value="tester", execution_result="success"),
        PriorStep(action_type="fill", description="fill password", target_selector="#p",
                  value="secret", execution_result="success"),
    ]
    out = StateSummarizer().summarize(active_goal="log in", verified_facts={}, prior_steps=steps)
    selectors = [e["selector"] for e in out["completed_nodes"]]
    assert selectors == ["#u", "#p"]


def test_ten_step_window_unchanged():
    steps = [PriorStep(action_type="click", description=f"step {i}", target_selector=f"#s{i}",
                       execution_result="success") for i in range(15)]
    out = StateSummarizer().summarize(active_goal="g", verified_facts={}, prior_steps=steps)
    assert len(out["completed_nodes"]) == 10
    assert out["completed_nodes"][0]["selector"] == "#s5"   # last-10 window preserved


def test_five_failure_cap_unchanged():
    steps = [PriorStep(action_type="click", description=f"fail {i}", target_selector=f"#f{i}",
                       execution_result=f"error {i}") for i in range(8)]
    out = StateSummarizer().summarize(active_goal="g", verified_facts={}, prior_steps=steps)
    assert len(out["important_failures"]) == 5


# ── page_changed inference (forward-compatible, best-effort) ────────────────

def test_page_changed_unknown_for_bare_success():
    assert _infer_page_changed("success") is None


def test_page_changed_false_when_text_says_unchanged():
    assert _infer_page_changed("success (page unchanged)") is False
    assert _infer_page_changed("succeeded, no change detected") is False


def test_page_changed_true_when_text_says_navigated():
    assert _infer_page_changed("success (page changed)") is True
    assert _infer_page_changed("navigated to result page") is True


def test_page_changed_none_for_empty_or_missing_result():
    assert _infer_page_changed("") is None
    assert _infer_page_changed(None) is None


def test_known_limitation_qualified_success_string_not_yet_routed_to_completed():
    """
    Documents the real, current limitation (see M1.1 deliverable notes): the classification
    gate in StateSummarizer.summarize() is an EXACT match against "success" (unchanged by
    M1.1 on purpose — that gate is not part of M1.1's scope). A progress-qualified string
    like "success (page unchanged)" therefore does NOT reach completed_nodes today; it is
    misrouted to important_failures. This is expected until a later milestone (M1.5) makes
    callers emit qualified strings AND updates this classification gate to match them.
    """
    step = PriorStep(action_type="click", description="click page 2", target_selector="#p2",
                     execution_result="success (page unchanged)")
    out = StateSummarizer().summarize(active_goal="g", verified_facts={}, prior_steps=[step])
    assert out["completed_nodes"] == []
    assert out["important_failures"] == [
        {"step": "click page 2", "error": "success (page unchanged)"}
    ]


# ── ContextCompressor ────────────────────────────────────────────────────────

def test_compress_surfaces_recent_actions_with_selector():
    step = PriorStep(action_type="click", description="click the '2' pagination link",
                     target_selector="#p2", execution_result="success")
    result = ContextCompressor().compress(
        task="navigate to page 2", page_context=_page(), verified_facts={}, prior_steps=[step])
    assert "recent_actions" in result
    assert result["recent_actions"][0]["selector"] == "#p2"
    assert result["recent_actions"][0]["action_type"] == "click"


def test_compress_recent_actions_empty_when_no_prior_steps():
    result = ContextCompressor().compress(
        task="t", page_context=_page(), verified_facts={}, prior_steps=[])
    assert result["recent_actions"] == []


def test_compress_important_failures_unaffected_by_the_change():
    step = PriorStep(action_type="click", description="click missing", target_selector="#x",
                     execution_result="not found")
    result = ContextCompressor().compress(
        task="t", page_context=_page(), verified_facts={}, prior_steps=[step])
    assert result["recent_actions"] == []
    assert result["important_failures"] == [{"step": "click missing", "error": "not found"}]


def test_compress_key_set_is_additive_not_breaking():
    """The new key is additive; every previously-required key is still present."""
    result = ContextCompressor().compress(
        task="t", page_context=_page(), verified_facts={"a": 1}, prior_steps=[])
    for key in ("verified_facts", "active_goal", "relevant_elements",
               "important_failures", "task_constraints"):
        assert key in result
    assert "recent_actions" in result


def test_compress_still_serializes_to_json():
    """The compressed dict must remain JSON-serializable — it is transmitted via
    json.dumps() in ai_service.analyze() without any changes to that call site."""
    import json
    step = PriorStep(action_type="fill", description="fill query", target_selector="#q",
                     value="python", execution_result="success")
    result = ContextCompressor().compress(
        task="search", page_context=_page(), verified_facts={}, prior_steps=[step])
    dumped = json.dumps(result)
    assert '"recent_actions"' in dumped
    assert '"#q"' in dumped


def test_compress_cognitive_context_still_optional_and_additive():
    """M1.1 must not disturb the existing optional 7th key."""
    result = ContextCompressor().compress(
        task="t", page_context=_page(), verified_facts={}, prior_steps=[])
    assert "cognitive_context" not in result
    result2 = ContextCompressor().compress(
        task="t", page_context=_page(), verified_facts={}, prior_steps=[],
        cognitive_context={"user_goal": "x"})
    assert result2["cognitive_context"] == {"user_goal": "x"}
    assert result2["recent_actions"] == []


def test_compress_preserves_goal_relevant_visible_content_in_verified_facts():
    result = ContextCompressor().compress(
        task="Tell me the invoice total",
        page_context=_page_with_content(
            text=(
                "Billing Summary Invoice Number INV-2026-0711 "
                "Subtotal INR 12,400.00 Tax INR 2,232.00 "
                "Total Due INR 14,632.00 Payment Terms Net 15"
            ),
        ),
        verified_facts={},
        prior_steps=[],
    )

    content = result["verified_facts"]["relevant_visible_content"]
    assert content == [{
        "selector": "section",
        "text": (
            "Billing Summary Invoice Number INV-2026-0711 "
            "Subtotal INR 12,400.00 Tax INR 2,232.00 "
            "Total Due INR 14,632.00 Payment Terms Net 15"
        ),
    }]


def test_compress_excludes_irrelevant_visible_content_noise():
    result = ContextCompressor().compress(
        task="Search flights",
        page_context=_page_with_content(
            text="Footer links Privacy Terms Careers Advertising Contact",
            visible_text="Footer links Privacy Terms Careers Advertising Contact",
        ),
        verified_facts={},
        prior_steps=[],
    )

    assert "relevant_visible_content" not in result["verified_facts"]


def test_compress_preserves_existing_verified_facts_when_adding_content():
    result = ContextCompressor().compress(
        task="Tell me the invoice total",
        page_context=_page_with_content(text="Total Due INR 14,632.00"),
        verified_facts={"status": "due"},
        prior_steps=[],
    )

    assert result["verified_facts"]["status"] == "due"
    assert "Total Due INR 14,632.00" in result["verified_facts"]["relevant_visible_content"][0]["text"]
