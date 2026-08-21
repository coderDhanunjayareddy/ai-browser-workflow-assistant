from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_live_sidepanel_validation.py"
SPEC = importlib.util.spec_from_file_location("live_sidepanel_harness", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_approved_file_and_no_send_report_is_not_misclassified_as_pending_approval() -> None:
    text = (
        "The broker evidence verifies one exact approved file. "
        "The affirmative task contains no send objective. WhatsApp. ✓ Done — 5 of 5 steps succeeded"
    )
    assert MODULE._looks_like_critical_approval(text.lower()) is False


def test_explicit_send_approval_prompt_remains_critical() -> None:
    text = "This WhatsApp message requires approval before send."
    assert MODULE._looks_like_critical_approval(text.lower()) is True
