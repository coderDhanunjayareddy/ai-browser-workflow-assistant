from __future__ import annotations

from app.semantic_execution_kernel.models import SemanticActionDefinition, SemanticActionType


def semantic_action_registry() -> list[SemanticActionDefinition]:
    return [
        _action("SEARCH_WEB", ["mission_running"], [], ["query_present"], ["search_page_loaded"], ["WAIT_FOR_STATE", "SKIP_ENTITY"]),
        _action("COLLECT_RESULTS", ["page_loaded"], [], ["entities_visible"], ["entities_registered"], ["WAIT_FOR_STATE", "READ_PAGE"]),
        _action("OPEN_ENTITY", ["entity_discovered"], ["entity"], ["entity_has_url_or_selector"], ["tab_exists", "url_matches", "page_loaded"], ["FOCUS_TAB", "SKIP_ENTITY"]),
        _action("FOCUS_TAB", ["tab_known"], [], ["tab_reference_valid"], ["focused_tab_matches"], ["OPEN_ENTITY"]),
        _action("READ_PAGE", ["page_loaded"], [], ["content_available"], ["page_analyzed"], ["WAIT_FOR_STATE", "SKIP_ENTITY"]),
        _action("EXTRACT_FIELDS", ["page_analyzed"], [], ["field_schema_present"], ["non_empty_structured_data"], ["READ_PAGE"]),
        _action("FILL_FORM", ["entity_discovered"], ["form"], ["field_bindings_exist"], ["field_value_changed"], ["WAIT_FOR_STATE"]),
        _action("UPLOAD_FILE", ["entity_discovered"], ["file"], ["file_available"], ["file_appears", "status_visible"], ["WAIT_FOR_STATE", "SKIP_ENTITY"]),
        _action("DOWNLOAD_FILE", ["entity_discovered"], ["link"], ["download_target_valid"], ["download_started", "download_completed"], ["OPEN_ENTITY"]),
        _action("CLICK_ENTITY", ["entity_discovered"], ["button"], ["selector_or_binding_exists"], ["dom_changed", "navigation_occurred"], ["WAIT_FOR_STATE", "OPEN_ENTITY"]),
        _action("WAIT_FOR_STATE", ["mission_running"], [], ["bounded_wait"], ["state_changed_or_timeout"], ["READ_PAGE"]),
        _action("MARK_COMPLETE", ["evidence_present"], [], ["completion_evidence_valid"], ["ledger_completed"], []),
        _action("SKIP_ENTITY", ["entity_discovered"], ["entity"], ["skip_reason_present"], ["ledger_skipped"], ["MARK_COMPLETE"]),
    ]


def get_action_definition(action_type: SemanticActionType) -> SemanticActionDefinition:
    for definition in semantic_action_registry():
        if definition.action_type == action_type:
            return definition
    raise KeyError(action_type)


def _action(
    action_type: SemanticActionType,
    required_state: list[str],
    required_entities: list[str],
    validation_rules: list[str],
    success_evidence: list[str],
    failure_transitions: list[str],
) -> SemanticActionDefinition:
    return SemanticActionDefinition(
        action_type=action_type,
        required_state=required_state,
        required_entities=required_entities,
        validation_rules=validation_rules,
        retry_policy={"max_attempts": 3},
        success_evidence=success_evidence,
        failure_transitions=failure_transitions,
    )
