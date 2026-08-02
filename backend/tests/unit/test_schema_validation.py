from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

import app.mission_result.persistence  # noqa: F401
from app.core.database import Base
from app.schema_validation import SchemaValidator


def test_schema_validator_detects_type_mismatch():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE mission_results (
                        mission_result_id VARCHAR PRIMARY KEY,
                        mission_id VARCHAR NOT NULL,
                        outcome VARCHAR NOT NULL,
                        final_answer TEXT NOT NULL,
                        report_format VARCHAR NOT NULL,
                        report_artifact_id VARCHAR,
                        knowledge_artifact_id VARCHAR,
                        completion_reason TEXT NOT NULL,
                        confidence VARCHAR NOT NULL,
                        result_metadata JSON,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME
                    )
                    """
                )
            )
        report = SchemaValidator(engine).compare()
        mismatches = [item for item in report.comparisons if item.object_name == "mission_results.confidence"]

        assert any(item.status == "TYPE MISMATCH" for item in mismatches)
    finally:
        engine.dispose()


def test_schema_validator_matches_create_all_tables():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    try:
        Base.metadata.create_all(bind=engine)
        report = SchemaValidator(engine).compare()

        assert not [
            item for item in report.comparisons
            if item.status == "MISSING" and item.object_name.startswith("mission_results")
        ]
    finally:
        engine.dispose()
