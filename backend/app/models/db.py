import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Text, JSON, Integer, Boolean
from sqlalchemy.orm import relationship

from app.core.database import Base


class CognitiveSessionRecord(Base):
    """
    Persisted cognitive state for one conversation.
    Loaded on cache-miss in CognitiveConversationManager; saved after each turn.
    entities_json / goal_json store serialized dataclass fields as JSON text.
    """
    __tablename__ = "cognitive_sessions"

    conversation_id      = Column(String, primary_key=True)
    turn_count           = Column(Integer, default=0, nullable=False)
    conversation_summary = Column(Text, default="")
    active_intent        = Column(String, default="unknown")
    entities_json        = Column(Text, default="[]")   # JSON list of entity dicts
    entity_order_json    = Column(Text, default="[]")   # JSON list of entity ids (insertion order)
    goal_json            = Column(Text, nullable=True)  # JSON goal dict or NULL
    created_at           = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at           = Column(DateTime, default=datetime.utcnow, nullable=False)


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


class RunLedgerEventRecord(Base):
    """V3.0 append-only canonical run ledger event.

    This table is additive and does not replace existing WorkflowEvent,
    timeline, mission, workspace, or benchmark trace records.
    """
    __tablename__ = "run_ledger_events"

    event_id = Column(String, primary_key=True)
    run_id = Column(String, nullable=False, index=True)
    step_index = Column(Integer, default=0, nullable=False)
    event_type = Column(String, nullable=False, index=True)
    schema_version = Column(String, nullable=False)
    producer = Column(String, nullable=False)
    payload = Column(JSON, default=dict)
    links = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


# ── V4.5 / V4.6 Unified Task Graph ───────────────────────────────────────────

class UnifiedTaskRecord(Base):
    """
    Persistence record for a UnifiedTask.
    V4.6: extended with intelligence_summary_json, restored_at, snapshot_count.
    Timeline and approval records live in separate tables.
    """
    __tablename__ = "unified_tasks"

    task_id                  = Column(String, primary_key=True)
    conversation_id          = Column(String, nullable=False, index=True)
    cognitive_session_id     = Column(String, nullable=True)
    research_session_id      = Column(String, nullable=True)
    workflow_session_id      = Column(String, nullable=True)
    original_query           = Column(Text, default="")
    current_goal             = Column(Text, nullable=True)
    state                    = Column(String, default="CREATED", nullable=False)
    approval_state           = Column(String, default="PENDING", nullable=False)
    entities_json            = Column(Text, default="{}")   # JSON dict
    execution_plan_json      = Column(Text, nullable=True)  # JSON dict or NULL
    research_report_json     = Column(Text, nullable=True)  # JSON dict or NULL
    intelligence_summary_json = Column(Text, nullable=True) # V4.6 JSON dict or NULL
    snapshot_count           = Column(Integer, default=0, nullable=False)
    restored_at              = Column(DateTime, nullable=True)
    created_at               = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at               = Column(DateTime, default=datetime.utcnow, nullable=False)

    timeline_records  = relationship("TaskTimelineRecord",  back_populates="task", cascade="all, delete-orphan")
    approval_records  = relationship("TaskApprovalRecord",  back_populates="task", cascade="all, delete-orphan")
    snapshot_records  = relationship("TaskSnapshotRecord",  back_populates="task", cascade="all, delete-orphan")


class TaskTimelineRecord(Base):
    """One persisted row per timeline event (V4.6)."""
    __tablename__ = "unified_task_timeline"

    event_id     = Column(String, primary_key=True)
    task_id      = Column(String, ForeignKey("unified_tasks.task_id", ondelete="CASCADE"), nullable=False, index=True)
    event_type   = Column(String, nullable=False)
    payload_json = Column(Text, default="{}")
    timestamp    = Column(DateTime, nullable=False)
    created_at   = Column(DateTime, default=datetime.utcnow, nullable=False)

    task = relationship("UnifiedTaskRecord", back_populates="timeline_records")


class TaskApprovalRecord(Base):
    """One persisted row per approval record (V4.6)."""
    __tablename__ = "unified_task_approvals"

    approval_id     = Column(String, primary_key=True)
    task_id         = Column(String, ForeignKey("unified_tasks.task_id", ondelete="CASCADE"), nullable=False, index=True)
    action          = Column(Text, nullable=False)
    risk_level      = Column(String, nullable=False)
    status          = Column(String, default="PENDING", nullable=False)
    resolution_note = Column(Text, default="")
    created_at      = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at     = Column(DateTime, nullable=True)

    task = relationship("UnifiedTaskRecord", back_populates="approval_records")


class TaskSnapshotRecord(Base):
    """Snapshot of a task's key context at a lifecycle milestone (V4.6)."""
    __tablename__ = "unified_task_snapshots"

    snapshot_id  = Column(String, primary_key=True)
    task_id      = Column(String, ForeignKey("unified_tasks.task_id", ondelete="CASCADE"), nullable=False, index=True)
    trigger      = Column(String, nullable=False)   # milestone name
    task_state   = Column(String, nullable=False)
    context_json = Column(Text, default="{}")
    created_at   = Column(DateTime, default=datetime.utcnow, nullable=False)

    task = relationship("UnifiedTaskRecord", back_populates="snapshot_records")


# ── V5.0 Mission Layer ────────────────────────────────────────────────────────

class MissionRecord(Base):
    """
    Persistence record for a Mission (V5.0).
    A mission groups multiple UnifiedTasks into one coherent objective.
    """
    __tablename__ = "missions"

    mission_id    = Column(String, primary_key=True)
    title         = Column(Text, default="")
    objective     = Column(Text, default="")
    state         = Column(String, default="CREATED", nullable=False)
    priority      = Column(Integer, default=3, nullable=False)  # 1=high … 5=low
    metadata_json = Column(Text, default="{}")
    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at    = Column(DateTime, default=datetime.utcnow, nullable=False)

    task_refs = relationship(
        "MissionTaskRecord",
        back_populates="mission",
        cascade="all, delete-orphan",
        order_by="MissionTaskRecord.position",
    )


class MissionTaskRecord(Base):
    """
    Junction table: Mission → Task (V5.0).
    task_id has no FK to unified_tasks because tasks may exist only in memory
    (mission_persistence can be enabled independently of unified_task_persistence).
    """
    __tablename__ = "mission_tasks"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    mission_id  = Column(String, ForeignKey("missions.mission_id", ondelete="CASCADE"),
                         nullable=False, index=True)
    task_id     = Column(String, nullable=False, index=True)
    position    = Column(Integer, default=0)
    attached_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    mission = relationship("MissionRecord", back_populates="task_refs")
