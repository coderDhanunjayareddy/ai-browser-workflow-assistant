from datetime import datetime

from sqlalchemy.orm import Session

from app.models.db import WorkflowEvent, WorkflowSession
from app.schemas.history import EventHistory, HistoryResponse, SessionHistory
from app.schemas.workflow import LogEventRequest, LogEventResponse


def log_event(db: Session, request: LogEventRequest) -> LogEventResponse:
    """
    Write an approval/rejection/execution event to the database.
    Creates the parent session row if it does not yet exist.
    """
    # Upsert the session — the extension sends the same session_id
    # for all events within one side panel open.
    session = db.get(WorkflowSession, request.session_id)
    if not session:
        session = WorkflowSession(
            id=request.session_id,
            tab_url=request.tab_url,
            tab_title=request.tab_title,
        )
        db.add(session)

    action = request.action
    now = datetime.utcnow()

    event = WorkflowEvent(
        session_id=request.session_id,
        event_type=request.event_type,
        action_type=action.action_type,
        target_selector=action.target_selector,
        value=action.value,
        description=action.description,
        ai_reasoning=action.reasoning,
        confidence=action.confidence,
        safety_level=action.safety_level,
        approved_at=now if request.event_type == "approved" else None,
        executed_at=now if request.event_type == "executed" else None,
        execution_result=request.execution_result if request.event_type == "executed" else None,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    return LogEventResponse(logged=True, event_id=event.id)


def get_history(db: Session, limit: int = 20) -> HistoryResponse:
    """
    Return the most recent sessions with all their events, newest first.
    """
    sessions = (
        db.query(WorkflowSession)
        .order_by(WorkflowSession.created_at.desc())
        .limit(limit)
        .all()
    )

    result: list[SessionHistory] = []
    for s in sessions:
        events = (
            db.query(WorkflowEvent)
            .filter(WorkflowEvent.session_id == s.id)
            .order_by(WorkflowEvent.created_at.asc())
            .all()
        )
        result.append(
            SessionHistory(
                id=s.id,
                tab_url=s.tab_url or "",
                tab_title=s.tab_title or "",
                status=s.status or "active",
                created_at=s.created_at.isoformat() if s.created_at else "",
                events=[
                    EventHistory(
                        id=e.id,
                        event_type=e.event_type,
                        action_type=e.action_type,
                        description=e.description,
                        target_selector=e.target_selector,
                        value=e.value,
                        execution_result=e.execution_result,
                        safety_level=e.safety_level,
                        confidence=e.confidence,
                        created_at=e.created_at.isoformat() if e.created_at else "",
                    )
                    for e in events
                ],
            )
        )

    return HistoryResponse(sessions=result, total=len(result))
