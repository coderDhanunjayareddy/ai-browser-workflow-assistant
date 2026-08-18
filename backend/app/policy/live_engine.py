from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from app.policy.engine import GovernanceDecisionEngine
from app.policy.live_store import LivePolicyStore, live_policy_store
from app.policy.models import (
    ConfirmationReceipt,
    LivePolicyDecision,
    LivePolicyRequest,
    OriginGrant,
    PolicyAuditEvent,
)
from app.schemas.response import SuggestedAction


KNOWN_ACTION_TYPES = {
    "click", "fill", "scroll", "navigate", "navigate_next_page", "wait",
    "select_option", "choose_date", "hover", "keyboard_shortcut",
    "open_new_tab", "switch_tab", "focus_existing_tab", "close_tab",
    "rich_text", "insert_rich_text", "edit_rich_text", "monaco_edit",
    "codemirror_edit", "shadow_fill", "clipboard", "drag_drop",
    "virtual_list_find", "shadow_click", "infinite_scroll", "advanced_keyboard",
    "canvas_action", "svg_action", "pdf_viewer", "chart_action", "map_action",
    "media_control", "file_preview", "visual_region", "google_workspace_adapter",
    "microsoft365_adapter", "github_advanced_adapter", "jira_adapter",
    "confluence_adapter", "slack_adapter", "notion_adapter", "figma_adapter",
    "canva_adapter", "salesforce_adapter", "sso_auth", "mfa_otp_handoff",
    "enterprise_file_workflow", "site_optimize",
}

ORIGIN_GRANT_ACTION_TYPES = {
    "click", "fill", "scroll", "navigate", "navigate_next_page", "wait",
    "select_option", "choose_date", "hover", "keyboard_shortcut",
    "open_new_tab", "switch_tab", "focus_existing_tab", "infinite_scroll",
    "virtual_list_find", "media_control", "file_preview",
}

INJECTION_STOP_LABELS = {
    "prompt_injection_detected",
    "instruction_override",
    "secret_exfiltration",
    "policy_bypass_request",
    "credential_request_from_content",
}
INJECTION_ESCALATE_LABELS = {
    "untrusted_instruction",
    "external_instruction",
    "tool_requested_side_effect",
}


def normalize_origin(value: str) -> str:
    parsed = urlparse(str(value or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("origin must be an absolute http/https URL")
    host = parsed.hostname.lower()
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme.lower()}://{host}{port}"


def action_digest(action: SuggestedAction, execution_contract: dict | None = None) -> str:
    payload = {
        "action_id": action.action_id,
        "action_type": action.action_type,
        "target_selector": action.target_selector,
        "value": action.value,
        "description": action.description,
        "grounding": action.grounding,
        "execution_contract": execution_contract or {},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_unexpired(value: datetime, now: datetime) -> bool:
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return normalized > now


class LivePolicyEngine:
    def __init__(self, *, store: LivePolicyStore | None = None) -> None:
        self.store = store or live_policy_store
        self.governance = GovernanceDecisionEngine()

    def evaluate(self, request: LivePolicyRequest) -> LivePolicyDecision:
        action = self._action(request)
        origin = normalize_origin(request.origin)
        digest = action_digest(action, request.execution_contract)
        injection_decision = self._injection_decision(request)
        contract_error = self._execution_contract_error(request, action, origin)

        if contract_error:
            decision = self._decision(
                request, action, origin, digest,
                policy_decision="block", risk_level="critical",
                reason=contract_error, hooks=["invalid_execution_contract"],
                approval_required=False, requires_handoff=False,
            )
        elif action.action_type not in KNOWN_ACTION_TYPES:
            decision = self._decision(
                request, action, origin, digest,
                policy_decision="block", risk_level="critical",
                reason="unknown_action_type", hooks=["invalid_action_contract"],
                approval_required=False, requires_handoff=False,
            )
        elif injection_decision == "block":
            decision = self._decision(
                request, action, origin, digest,
                policy_decision="block", risk_level="critical",
                reason="prompt_injection_stop", hooks=["prompt_injection"],
                approval_required=False, requires_handoff=False,
            )
        elif injection_decision == "handoff_required":
            decision = self._decision(
                request, action, origin, digest,
                policy_decision="handoff_required", risk_level="critical",
                reason="untrusted_instruction_requires_handoff", hooks=["prompt_injection_escalation"],
                approval_required=True, requires_handoff=True,
            )
        else:
            governance, _ = self.governance.evaluate_action(
                run_id=request.session_id,
                mission_id=request.session_id,
                step_id=action.action_id,
                action=action,
            )
            decision = self._decision(
                request, action, origin, digest,
                policy_decision=governance.policy_decision,
                risk_level=governance.risk_level,
                reason=governance.decision_reason,
                hooks=list(governance.approval_hooks),
                approval_required=governance.approval_required,
                requires_handoff=governance.requires_handoff,
            )

        self._audit(decision, "evaluated", decision.decision_reason)
        return decision

    def issue_confirmation(self, request: LivePolicyRequest, *, ttl_seconds: int = 120) -> ConfirmationReceipt:
        decision = self.evaluate(request)
        if decision.policy_decision != "allow_with_confirmation":
            raise ValueError("confirmation receipts are only issued for confirmable actions")
        ttl = max(1, min(int(ttl_seconds), 300))
        receipt = ConfirmationReceipt(
            session_id=decision.session_id,
            action_id=decision.action_id,
            action_digest=decision.action_digest,
            origin=decision.origin,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl),
        )
        self.store.add_receipt(receipt)
        self.store.record(PolicyAuditEvent(
            event_type="confirmation_issued", session_id=receipt.session_id,
            action_id=receipt.action_id, origin=receipt.origin,
            policy_decision="allow_with_confirmation",
            reason="human_confirmation_recorded",
            metadata={"receipt_id": receipt.receipt_id, "expires_at": receipt.expires_at.isoformat()},
        ))
        return receipt

    def issue_origin_grant(
        self,
        *,
        session_id: str,
        origin: str,
        action_types: list[str],
        ttl_seconds: int = 900,
    ) -> OriginGrant:
        normalized = normalize_origin(origin)
        scoped = sorted(set(action_types))
        if not scoped or any(action_type not in ORIGIN_GRANT_ACTION_TYPES for action_type in scoped):
            raise ValueError("origin grant contains an unknown or consequential action type")
        ttl = max(1, min(int(ttl_seconds), 3600))
        grant = OriginGrant(
            session_id=session_id,
            origin=normalized,
            action_types=scoped,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl),
        )
        self.store.add_grant(grant)
        self.store.record(PolicyAuditEvent(
            event_type="origin_grant_issued", session_id=session_id, origin=normalized,
            reason="human_origin_grant_recorded",
            metadata={"grant_id": grant.grant_id, "action_types": scoped, "expires_at": grant.expires_at.isoformat()},
        ))
        return grant

    def revoke_origin_grant(self, grant_id: str) -> OriginGrant:
        grant = self.store.revoke_grant(grant_id)
        if grant is None:
            raise ValueError("origin grant not found or already revoked")
        self.store.record(PolicyAuditEvent(
            event_type="origin_grant_revoked", session_id=grant.session_id, origin=grant.origin,
            reason="human_origin_grant_revoked", metadata={"grant_id": grant.grant_id},
        ))
        return grant

    def enforce(self, request: LivePolicyRequest) -> LivePolicyDecision:
        decision = self.evaluate(request)
        if decision.policy_decision in {"block", "handoff_required", "defer"}:
            self._audit(decision, "execution_denied", decision.decision_reason)
            return decision

        if decision.policy_decision == "allow_with_confirmation":
            receipt = self.store.get_receipt(request.confirmation_receipt_id)
            now = datetime.now(timezone.utc)
            valid = bool(
                receipt
                and receipt.consumed_at is None
                and _is_unexpired(receipt.expires_at, now)
                and receipt.session_id == decision.session_id
                and receipt.origin == decision.origin
                and receipt.action_id == decision.action_id
                and receipt.action_digest == decision.action_digest
            )
            if not valid:
                denied = decision.model_copy(update={"allowed": False, "decision_reason": "valid_confirmation_receipt_required"})
                self._audit(denied, "execution_denied", denied.decision_reason)
                return denied
            consumed = self.store.consume_receipt(receipt.receipt_id)
            if consumed is None:
                denied = decision.model_copy(update={"allowed": False, "decision_reason": "confirmation_receipt_already_consumed"})
                self._audit(denied, "execution_denied", denied.decision_reason)
                return denied
            allowed = decision.model_copy(update={"allowed": True, "receipt_id": consumed.receipt_id})
            self.store.record(PolicyAuditEvent(
                event_type="receipt_consumed", session_id=allowed.session_id,
                action_id=allowed.action_id, origin=allowed.origin,
                decision_id=allowed.decision_id, policy_decision=allowed.policy_decision,
                reason="narrow_confirmation_receipt_consumed",
                metadata={"receipt_id": consumed.receipt_id},
            ))
            self._audit(allowed, "execution_allowed", "confirmed_action_allowed")
            return allowed

        if decision.policy_decision == "warn":
            grant = self.store.get_grant(request.origin_grant_id)
            now = datetime.now(timezone.utc)
            valid = bool(
                grant
                and grant.revoked_at is None
                and _is_unexpired(grant.expires_at, now)
                and grant.session_id == decision.session_id
                and grant.origin == decision.origin
                and self._action(request).action_type in grant.action_types
            )
            if not valid:
                denied = decision.model_copy(update={"allowed": False, "decision_reason": "valid_origin_grant_required"})
                self._audit(denied, "execution_denied", denied.decision_reason)
                return denied
            decision = decision.model_copy(update={"origin_grant_id": grant.grant_id})

        allowed = decision.model_copy(update={"allowed": True})
        self._audit(allowed, "execution_allowed", "policy_allow")
        return allowed

    def _action(self, request: LivePolicyRequest) -> SuggestedAction:
        payload = dict(request.action)
        payload["target_selector"] = str(payload.get("target_selector") or "")
        payload.setdefault("description", "")
        payload.setdefault("reasoning", "")
        payload.setdefault("confidence", 0.0)
        payload.setdefault("safety_level", "danger")
        return SuggestedAction.model_validate(payload)

    @staticmethod
    def _execution_contract_error(request: LivePolicyRequest, action: SuggestedAction, origin: str) -> str | None:
        contract = request.execution_contract
        if contract.get("schema_version") != "1.0":
            return "canonical_execution_contract_required"
        contract_action = contract.get("action")
        target = contract.get("target_identity")
        binding = contract.get("browser_binding")
        contract_origin = contract.get("origin")
        resource = contract.get("resource_identity")
        expected = contract.get("expected_effect")
        grounding_policy = contract.get("grounding_policy")
        if not all(isinstance(item, dict) for item in (contract_action, target, binding, contract_origin, resource, expected, grounding_policy)):
            return "malformed_execution_contract"
        if grounding_policy.get("ordered_sources") != ["stable_selector", "accessibility_name", "verified_screenshot"]:
            return "execution_contract_grounding_order_invalid"
        if grounding_policy.get("accessibility_requires_exact_name") is not True:
            return "execution_contract_accessibility_binding_invalid"
        if grounding_policy.get("screenshot_coordinates_verified") is True:
            action_grounding = contract_action.get("grounding") or {}
            if (
                action_grounding.get("source") != "vision_region"
                or action_grounding.get("screenshot_verified") is not True
                or not str(grounding_policy.get("screenshot_hash") or "").strip()
            ):
                return "execution_contract_screenshot_binding_invalid"
        immutable_fields = ("action_id", "action_type", "target_selector", "value", "safety_level")
        action_payload = action.model_dump(mode="json")
        if any(contract_action.get(field) != action_payload.get(field) for field in immutable_fields):
            return "execution_contract_action_mismatch"
        if target.get("selector") != action.target_selector:
            return "execution_contract_target_mismatch"
        if contract.get("safety_class") != action.safety_level:
            return "execution_contract_safety_mismatch"
        if not str(contract.get("idempotency_key") or "").strip():
            return "execution_contract_idempotency_missing"
        if not isinstance(binding.get("tab_id"), int) or not str(binding.get("frame_id") or "").strip():
            return "execution_contract_browser_binding_invalid"
        observed_url = str(contract_origin.get("observed_url") or "")
        try:
            if normalize_origin(observed_url) != origin or str(contract_origin.get("origin") or "") != origin:
                return "execution_contract_origin_mismatch"
        except ValueError:
            return "execution_contract_origin_mismatch"
        if resource.get("url") != observed_url:
            return "execution_contract_resource_mismatch"
        if action.action_type == "click" and not str(target.get("selector") or "").strip():
            return "execution_contract_click_target_missing"
        return None

    @staticmethod
    def _injection_decision(request: LivePolicyRequest) -> str | None:
        labels = {
            label
            for provenance in request.provenance
            if provenance.trust == "untrusted" and provenance.source_type in {"page", "tool"}
            for label in provenance.labels
        }
        if labels & INJECTION_STOP_LABELS:
            return "block"
        if labels & INJECTION_ESCALATE_LABELS:
            return "handoff_required"
        return None

    @staticmethod
    def _decision(
        request: LivePolicyRequest,
        action: SuggestedAction,
        origin: str,
        digest: str,
        *,
        policy_decision: str,
        risk_level: str,
        reason: str,
        hooks: list[str],
        approval_required: bool,
        requires_handoff: bool,
    ) -> LivePolicyDecision:
        return LivePolicyDecision(
            session_id=request.session_id,
            action_id=action.action_id,
            action_digest=digest,
            origin=origin,
            policy_decision=policy_decision,
            allowed=False,
            approval_required=approval_required,
            requires_handoff=requires_handoff,
            risk_level=risk_level,
            decision_reason=reason,
            approval_hooks=hooks,
            provenance=list(request.provenance),
        )

    def _audit(self, decision: LivePolicyDecision, event_type: str, reason: str) -> None:
        self.store.record(PolicyAuditEvent(
            event_type=event_type,
            session_id=decision.session_id,
            action_id=decision.action_id,
            origin=decision.origin,
            decision_id=decision.decision_id,
            policy_decision=decision.policy_decision,
            reason=reason,
            metadata={
                "risk_level": decision.risk_level,
                "approval_hooks": list(decision.approval_hooks),
                "action_digest": decision.action_digest,
            },
        ))


live_policy_engine = LivePolicyEngine()
