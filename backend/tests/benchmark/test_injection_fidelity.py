"""
M0 drift-guard — injected_scripts.js must stay faithful to the production content scripts.

The benchmark's Mode-B fidelity depends on injected_scripts.js being a verbatim port of
extension/src/content/{executor_v2,extractor_v2}.ts. These tests fail if the two diverge in
the ways that matter: the set of supported action cases and the fill() event-dispatch order.
When you intentionally change the .ts, update injected_scripts.js and these expectations.
"""
import os
import re

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(_HERE, "..", ".."))
REPO = os.path.abspath(os.path.join(BACKEND, ".."))
JS = os.path.join(BACKEND, "benchmark", "injected_scripts.js")
EXECUTOR_TS = os.path.join(REPO, "extension", "src", "content", "executor_v2.ts")
EXTRACTOR_TS = os.path.join(REPO, "extension", "src", "content", "extractor_v2.ts")


def _read(p):
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def test_js_exists_and_exposes_globals():
    js = _read(JS)
    assert "window.__m0Extract__" in js
    assert "window.__m0Execute__" in js


@pytest.mark.skipif(not os.path.exists(EXECUTOR_TS), reason="extension source not present")
def test_action_cases_match_executor_ts():
    ts = _read(EXECUTOR_TS)
    js = _read(JS)
    ts_cases = set(re.findall(r"case '([a-z_]+)':", ts))
    js_cases = set(re.findall(r"case '([a-z_]+)':", js))
    assert ts_cases, "no cases found in executor_v2.ts (parsing changed?)"
    missing = ts_cases - js_cases
    assert not missing, f"injected JS missing action cases present in TS: {missing}"


def test_fill_dispatch_order_preserved():
    js = _read(JS)
    # fill() must fire 'input' before 'change' (controlled-input behaviour)
    i_input = js.find("new Event('input'")
    i_change = js.find("new Event('change'")
    assert 0 < i_input < i_change, "fill() must dispatch input before change"


@pytest.mark.skipif(not os.path.exists(EXTRACTOR_TS), reason="extension source not present")
def test_extractor_pii_redaction_preserved():
    ts = _read(EXTRACTOR_TS)
    js = _read(JS)
    # the SSN + card redaction must be carried over verbatim
    assert "[redacted-ssn]" in ts and "[redacted-ssn]" in js
    assert "[redacted-card]" in ts and "[redacted-card]" in js


def test_extractor_caps_preserved():
    js = _read(JS)
    assert "MAX_ELEMENTS = 150" in js
    assert "MAX_TEXT_LENGTH = 1000" in js


# ── M1.2: observation completeness (value/checked/selected capture) ─────────

@pytest.mark.skipif(not os.path.exists(EXTRACTOR_TS), reason="extension source not present")
def test_value_capture_present_in_both_files():
    ts, js = _read(EXTRACTOR_TS), _read(JS)
    for marker in ("MAX_VALUE_LENGTH", "checkbox", "selected_text", "contenteditable"):
        assert marker in ts, f"{marker} missing from extractor_v2.ts"
        assert marker in js, f"{marker} missing from injected_scripts.js"


def test_password_fields_excluded_from_value_capture_in_both_files():
    ts, js = _read(EXTRACTOR_TS), _read(JS)
    for src, name in ((ts, "extractor_v2.ts"), (js, "injected_scripts.js")):
        assert "'password'" in src, f"password exclusion missing from {name}"
        assert "state['filled']" in src, f"password filled-state missing from {name}"
        # the exclusion must sit on the same branch that guards state['value'] capture
        idx = src.find("el.type !== 'password'")
        assert idx != -1, f"password exclusion condition missing from {name}"
        assert "state['value']" in src[idx:idx + 400], (
            f"password exclusion in {name} is not guarding the value-capture branch")


def test_checked_uses_native_property_in_both_files():
    ts, js = _read(EXTRACTOR_TS), _read(JS)
    assert "state['checked'] = el.checked" in ts
    assert "state['checked'] = el.checked" in js


def test_details_open_state_in_both_files():
    ts, js = _read(EXTRACTOR_TS), _read(JS)
    assert "DETAILS" in ts and "DETAILS" in js


# ── M-G1: candidate-generation coverage (summary is a native disclosure control) ──

@pytest.mark.skipif(not os.path.exists(EXTRACTOR_TS), reason="extension source not present")
def test_summary_tag_is_candidate_in_both_files():
    ts, js = _read(EXTRACTOR_TS), _read(JS)
    for src, name in ((ts, "extractor_v2.ts"), (js, "injected_scripts.js")):
        m = re.search(r"INTERACTIVE_SELECTOR\s*=\s*\[(.*?)\]\.join", src, re.DOTALL)
        assert m, f"INTERACTIVE_SELECTOR array not found in {name}"
        selectors = re.findall(r"'([^']*)'", m.group(1))
        assert "summary" in selectors, f"'summary' missing from INTERACTIVE_SELECTOR in {name}"


# ── Amazon Search Action Selection: submit/button/image/reset inputs are buttons ──

@pytest.mark.skipif(not os.path.exists(EXTRACTOR_TS), reason="extension source not present")
def test_submit_button_inputs_get_button_role_in_both_files():
    ts, js = _read(EXTRACTOR_TS), _read(JS)
    for src, name in ((ts, "extractor_v2.ts"), (js, "injected_scripts.js")):
        assert "type === 'submit'" in src and "type === 'button'" in src, (
            f"submit/button role mapping missing from {name}")
        assert "type === 'image'" in src and "type === 'reset'" in src, (
            f"image/reset role mapping missing from {name}")


# ── Unique selector generation: buildSelector must verify uniqueness ──────────

@pytest.mark.skipif(not os.path.exists(EXTRACTOR_TS), reason="extension source not present")
def test_build_selector_verifies_uniqueness_in_both_files():
    ts, js = _read(EXTRACTOR_TS), _read(JS)
    for src, name in ((ts, "extractor_v2.ts"), (js, "injected_scripts.js")):
        assert "isUnique" in src, f"uniqueness verification helper missing from {name}"
        assert "querySelectorAll" in src, f"buildSelector must query the DOM to verify in {name}"
        # the old unconditional depth cap must be gone (it produced non-unique paths)
        assert "depth < 5" not in src, f"stale depth-capped structural path still present in {name}"
