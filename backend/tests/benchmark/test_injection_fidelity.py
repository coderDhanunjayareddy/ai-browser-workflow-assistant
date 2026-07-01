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
