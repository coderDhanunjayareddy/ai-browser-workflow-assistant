import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Text, JSON, Integer, Boolean
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
    states = relationship("WorkflowState", back_populates="session")
    nodes  = relationship("TaskNode", back_populates="session")
    failures = relationship("FailureRecord", back_populates="session")
    budget = relationship("WorkflowBudgetRecord", back_populates="session", uselist=False)
    cost_metrics = relationship("WorkflowCostMetric", back_populates="session", uselist=False)


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


class WorkflowState(Base):
    """Stores key-value verified facts for a session."""
    __tablename__ = "workflow_states"

    id         = Column(String, primary_key=True, default=_new_uuid)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    facts      = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    session = relationship("WorkflowSession", back_populates="states")


class TaskNode(Base):
    """Represents a single step in a task graph execution."""
    __tablename__ = "task_nodes"

    id            = Column(String, primary_key=True, default=_new_uuid)
    session_id    = Column(String, ForeignKey("sessions.id"), nullable=False)
    node_id       = Column(String, nullable=False)
    description   = Column(Text)
    status        = Column(String, default="pending")  # pending, active, completed, failed
    prerequisites = Column(JSON, default=list)
    validators    = Column(JSON, default=list)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    session = relationship("WorkflowSession", back_populates="nodes")


class FailureRecord(Base):
    """Tracks automation failures and recovery results."""
    __tablename__ = "failure_records"

    id                 = Column(String, primary_key=True, default=_new_uuid)
    session_id         = Column(String, ForeignKey("sessions.id"), nullable=False)
    node_id            = Column(String)
    error_code         = Column(String, nullable=False)  # e.g., SELECTOR_STALE
    selector_used      = Column(Text)
    recovery_attempted = Column(String)
    recovery_success   = Column(Boolean, default=False)
    timestamp          = Column(DateTime, default=datetime.utcnow)

    session = relationship("WorkflowSession", back_populates="failures")


class HeuristicRecord(Base):
    """Logs the learning stats for selectors and site recovery rules."""
    __tablename__ = "heuristic_records"

    id            = Column(String, primary_key=True, default=_new_uuid)
    site_domain   = Column(String, nullable=False)
    failure_code  = Column(String, nullable=False)
    remedy_code   = Column(String, nullable=False)
    success_count = Column(Integer, default=0)
    attempt_count = Column(Integer, default=0)


class WorkflowBudgetRecord(Base):
    __tablename__ = "workflow_budgets"

    session_id = Column(String, ForeignKey("sessions.id"), primary_key=True)
    max_steps = Column(Integer, default=50, nullable=False)
    max_tokens = Column(Integer, default=50000, nullable=False)
    max_retries = Column(Integer, default=5, nullable=False)
    max_duration_seconds = Column(Integer, default=300, nullable=False)
    steps_used = Column(Integer, default=0, nullable=False)
    tokens_used = Column(Integer, default=0, nullable=False)
    retries_used = Column(Integer, default=0, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    session = relationship("WorkflowSession", back_populates="budget")


class WorkflowCostMetric(Base):
    __tablename__ = "workflow_cost_metrics"

    session_id = Column(String, ForeignKey("sessions.id"), primary_key=True)
    planner_calls = Column(Integer, default=0, nullable=False)
    vision_calls = Column(Integer, default=0, nullable=False)
    tokens_used = Column(Integer, default=0, nullable=False)
    planning_latency_ms = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    session = relationship("WorkflowSession", back_populates="cost_metrics")
