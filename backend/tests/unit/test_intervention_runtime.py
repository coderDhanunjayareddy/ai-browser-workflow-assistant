from __future__ import annotations

import pytest

from app.intervention_runtime import (
    create_authentication_intervention,
    create_captcha_intervention,
    create_mfa_intervention,
)
from app.schemas.request import PageContext


def page(*, url: str = "https://portal.example.test/login", tab_id: int | None = 9) -> PageContext:
    return PageContext(
        tab_id=tab_id,
        url=url,
        title="Portal",
        metadata={},
        interactive_elements=[],
        content_blocks=[],
        headings=[],
        selected_text="",
        visible_text="Sign in",
        images=[],
    )


def test_authentication_checkpoint_is_stable_and_provider_neutral() -> None:
    first = create_authentication_intervention(
        session_id="mission-1", objective_hint="open requested workspace", page_context=page()
    )
    second = create_authentication_intervention(
        session_id="mission-1", objective_hint="open requested workspace", page_context=page()
    )

    assert first.intervention_id == second.intervention_id
    assert first.checkpoint_ref == second.checkpoint_ref
    assert first.resume_condition.observed_origin == "https://portal.example.test"
    assert first.resume_condition.tab_id == 9
    assert first.secret_handling == "direct_browser_only"
    assert not any(name in str(first.model_dump()).casefold() for name in ("whatsapp", "gmail", "linkedin"))


@pytest.mark.parametrize("url", ["chrome://settings", "about:blank", "not-a-url"])
def test_intervention_rejects_unbound_or_privileged_origins(url: str) -> None:
    with pytest.raises(ValueError, match=r"HTTP\(S\) origin"):
        create_authentication_intervention(
            session_id="mission-1", objective_hint="open workspace", page_context=page(url=url)
        )


def test_intervention_rejects_missing_tab_binding() -> None:
    with pytest.raises(ValueError, match="tab id"):
        create_authentication_intervention(
            session_id="mission-1", objective_hint="open workspace", page_context=page(tab_id=None)
        )


def test_mfa_and_captcha_use_distinct_stable_generic_contracts() -> None:
    mfa = create_mfa_intervention(
        session_id="mission-1", objective_hint="continue workspace", page_context=page()
    )
    captcha = create_captcha_intervention(
        session_id="mission-1", objective_hint="continue workspace", page_context=page()
    )

    assert mfa.kind == "mfa"
    assert mfa.resume_condition.evidence_kind == "authenticated_state"
    assert captcha.kind == "captcha"
    assert captcha.resume_condition.evidence_kind == "element_absent"
    assert mfa.intervention_id != captcha.intervention_id
