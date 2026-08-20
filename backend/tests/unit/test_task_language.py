from app.execution_orchestrator.completion_engine import _targets
from app.execution_orchestrator.phase_state_machine import workflow_category
from app.mission.intelligence.blueprint_builder import _is_upload_workflow
from app.task_language import affirmative_task_text


OPEN_ONLY_WHATSAPP_TASK = (
    "Open WhatsApp and open the exact direct chat named Teja Spc. "
    "Do not type a message, attach a file, or send anything."
)


def test_negative_action_clause_is_removed_as_one_scoped_constraint() -> None:
    normalized = affirmative_task_text(OPEN_ONLY_WHATSAPP_TASK)

    assert "open whatsapp" in normalized
    assert "attach" not in normalized
    assert "send" not in normalized
    assert "type" not in normalized


def test_negative_attachment_does_not_create_upload_blueprint_or_target() -> None:
    assert _is_upload_workflow(OPEN_ONLY_WHATSAPP_TASK) is False
    assert workflow_category(OPEN_ONLY_WHATSAPP_TASK) == "interactive_browser_task"
    assert "uploaded_files" not in _targets(OPEN_ONLY_WHATSAPP_TASK)


def test_affirmative_attachment_still_creates_upload_blueprint_and_target() -> None:
    task = "Open WhatsApp, open chat Teja Spc, and attach the approved file."

    assert _is_upload_workflow(task) is True
    assert workflow_category(task) == "file_upload"
    assert _targets(task)["uploaded_files"] == 1


def test_media_playback_is_an_interactive_browser_workflow() -> None:
    assert workflow_category("Play Telugu music on YouTube") == "interactive_browser_task"
