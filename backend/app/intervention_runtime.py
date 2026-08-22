from __future__ import annotations

import hashlib
from urllib.parse import urlparse

from app.contracts.intervention import (
    HumanInterventionRequest,
    InterventionKind,
    ResumeCondition,
    ResumeEvidenceKind,
)
from app.schemas.request import PageContext


def browser_origin(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Human intervention requires an observed HTTP(S) origin.")
    return f"{parsed.scheme}://{parsed.netloc}"


def create_browser_intervention(
    *,
    session_id: str,
    objective_hint: str,
    page_context: PageContext,
    kind: InterventionKind,
    reason_code: str,
    user_message: str,
    requested_action: str,
    evidence_kind: ResumeEvidenceKind,
    expected_value: str,
) -> HumanInterventionRequest:
    """Create a stable, provider-neutral checkpoint for a human-only browser gate.

    Provider names, selectors, credentials, and site procedures are deliberately
    absent. The extension owns live tab binding and post-intervention evidence.
    """
    origin = browser_origin(page_context.url)
    tab_id = page_context.tab_id
    if tab_id is None:
        raise ValueError("Human intervention requires an observed browser tab id.")
    identity = f"{session_id}|{kind}|{objective_hint.strip().casefold()}|{origin}|{tab_id}|{page_context.frame_id}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    objective_id = f"objective_{kind}_{digest}"
    return HumanInterventionRequest(
        run_id=session_id,
        intervention_id=f"intervention_{digest}",
        mission_id=session_id,
        objective_id=objective_id,
        kind=kind,
        reason_code=reason_code,
        user_message=user_message,
        requested_action=requested_action,
        secret_handling="direct_browser_only",
        checkpoint_ref=f"checkpoint_{digest}",
        completed_objective_ids=[],
        pending_objective_ids=[objective_id],
        resume_condition=ResumeCondition(
            evidence_kind=evidence_kind,
            expected_value=expected_value,
            observed_origin=origin,
            tab_id=tab_id,
            frame_id=page_context.frame_id,
        ),
        request_budget=2,
    )


def create_authentication_intervention(
    *, session_id: str, objective_hint: str, page_context: PageContext,
) -> HumanInterventionRequest:
    return create_browser_intervention(
        session_id=session_id,
        objective_hint=objective_hint,
        page_context=page_context,
        kind="authentication",
        reason_code="authentication_required",
        user_message="Authentication is required before this objective can continue.",
        requested_action="Complete the visible sign-in step directly in this browser tab, then ask the assistant to verify and resume.",
        evidence_kind="authenticated_state",
        expected_value="the observed authentication gate is absent and the destination workspace is visible",
    )


def create_mfa_intervention(
    *, session_id: str, objective_hint: str, page_context: PageContext,
) -> HumanInterventionRequest:
    return create_browser_intervention(
        session_id=session_id,
        objective_hint=objective_hint,
        page_context=page_context,
        kind="mfa",
        reason_code="mfa_required",
        user_message="A multi-factor verification step is required before this objective can continue.",
        requested_action="Complete the visible verification step directly in this browser tab, then ask the assistant to verify and resume.",
        evidence_kind="authenticated_state",
        expected_value="the observed multi-factor gate is absent and the destination workspace is visible",
    )


def create_captcha_intervention(
    *, session_id: str, objective_hint: str, page_context: PageContext,
) -> HumanInterventionRequest:
    return create_browser_intervention(
        session_id=session_id,
        objective_hint=objective_hint,
        page_context=page_context,
        kind="captcha",
        reason_code="captcha_required",
        user_message="A human-verification challenge is blocking the current objective.",
        requested_action="Complete the visible challenge directly in this browser tab, then ask the assistant to verify and resume.",
        evidence_kind="element_absent",
        expected_value="the observed human-verification challenge is absent",
    )
