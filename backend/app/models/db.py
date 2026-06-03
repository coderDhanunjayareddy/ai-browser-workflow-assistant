import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class WorkflowSession(Base):
    """
    One session per side panel open. Groups all events for a single
    user interaction with a specific page.
    """
    __tablename__ = "sessions"

    id         = Column(String, primary_key=True, default=_new_uuid)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    tab_url    = Column(Text, default="")
    tab_title  = Column(Text, default="")
    status     = Column(String, default="active")  # active | completed | abandoned

    events = relationship("WorkflowEvent", back_populates="session")


class WorkflowEvent(Base):
    """
    One row per action decision: suggested → approved/rejected → executed.
    Full audit trail of every AI suggestion and user decision.
    """
    __tablename__ = "workflow_events"

    id               = Column(String, primary_key=True, default=_new_uuid)
    session_id       = Column(String, ForeignKey("sessions.id"), nullable=False)
    event_type       = Column(String, nullable=False)  # approved | rejected | executed
    action_type      = Column(String)                  # click | fill | scroll | navigate
    target_selector  = Column(Text)
    value            = Column(Text)
    description      = Column(Text)
    ai_reasoning     = Column(Text)
    confidence       = Column(Float)
    safety_level     = Column(String)
    approved_at      = Column(DateTime)
    executed_at      = Column(DateTime)
    execution_result = Column(String)                  # success | failure | element_not_found
    created_at       = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("WorkflowSession", back_populates="events")
