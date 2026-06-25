"""
Shared pytest fixtures for V4.6 persistence tests.

Provides a SQLite in-memory engine + session factory that is injected into
all persistence modules so tests run without PostgreSQL.

StaticPool is required: SQLite :memory: databases are per-connection.
Without StaticPool, each new Session opens a fresh empty connection, making
tables created by create_all() invisible to later sessions.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
import app.models.db  # noqa: F401 — registers all ORM models with Base


@pytest.fixture(scope="session")
def sqlite_engine():
    """
    One shared SQLite in-memory engine for the entire test session.
    StaticPool ensures all sessions share the same underlying DB connection.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="session")
def sqlite_session_factory(sqlite_engine):
    return sessionmaker(bind=sqlite_engine, autocommit=False, autoflush=False)


@pytest.fixture(autouse=True)
def inject_test_db(sqlite_session_factory, request):
    """
    Auto-inject SQLite session factory into persistence modules for test_v46_*
    and test_v50_* files. Other tests are unaffected.
    """
    test_file = request.node.fspath.basename

    # ── V4.6 injection ────────────────────────────────────────────────────────
    if test_file.startswith("test_v46"):
        from app.unified import (
            persistence as task_persistence,
            timeline_persistence,
            approval_persistence,
            snapshot,
        )

        task_persistence._set_session_factory(sqlite_session_factory)
        timeline_persistence._set_session_factory(sqlite_session_factory)
        approval_persistence._set_session_factory(sqlite_session_factory)
        snapshot._set_session_factory(sqlite_session_factory)

        from app.core.config import settings as _settings
        _orig = _settings.unified_task_persistence
        _settings.unified_task_persistence = True

        yield

        _settings.unified_task_persistence = _orig

        with sqlite_session_factory() as db:
            from app.models.db import (
                UnifiedTaskRecord, TaskTimelineRecord,
                TaskApprovalRecord, TaskSnapshotRecord,
            )
            db.query(TaskSnapshotRecord).delete()
            db.query(TaskApprovalRecord).delete()
            db.query(TaskTimelineRecord).delete()
            db.query(UnifiedTaskRecord).delete()
            db.commit()

        task_persistence._reset_session_factory()
        timeline_persistence._reset_session_factory()
        approval_persistence._reset_session_factory()
        snapshot._reset_session_factory()

    # ── V5.0 injection ────────────────────────────────────────────────────────
    elif test_file.startswith("test_v50"):
        from app.mission import persistence as mission_persistence
        mission_persistence._set_session_factory(sqlite_session_factory)

        from app.core.config import settings as _settings
        _orig = _settings.mission_persistence
        _settings.mission_persistence = True

        yield

        _settings.mission_persistence = _orig

        with sqlite_session_factory() as db:
            from app.models.db import MissionTaskRecord, MissionRecord
            db.query(MissionTaskRecord).delete()
            db.query(MissionRecord).delete()
            db.commit()

        mission_persistence._reset_session_factory()

        # Reset in-memory mission store between tests
        from app.mission import store as mission_store
        mission_store._reset_for_testing()

    else:
        yield
