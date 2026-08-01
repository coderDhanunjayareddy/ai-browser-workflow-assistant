from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class MissionResultRecord(Base):
    __tablename__ = "mission_results"

    mission_result_id = Column(String, primary_key=True)
    mission_id = Column(String, nullable=False, index=True)
    outcome = Column(String, nullable=False, index=True)
    final_answer = Column(Text, default="", nullable=False)
    report_format = Column(String, default="markdown", nullable=False)
    report_artifact_id = Column(String, nullable=True, index=True)
    knowledge_artifact_id = Column(String, nullable=True, index=True)
    completion_reason = Column(Text, default="", nullable=False)
    confidence = Column(Float, default=0.0, nullable=False)
    result_metadata = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    artifacts = relationship("MissionResultArtifactRecord", back_populates="result", cascade="all, delete-orphan")
    versions = relationship("MissionResultVersionRecord", back_populates="result", cascade="all, delete-orphan")


class MissionResultArtifactRecord(Base):
    __tablename__ = "mission_result_artifacts"

    artifact_id = Column(String, primary_key=True)
    mission_result_id = Column(String, ForeignKey("mission_results.mission_result_id", ondelete="CASCADE"), nullable=False, index=True)
    mission_id = Column(String, nullable=False, index=True)
    kind = Column(String, nullable=False, index=True)
    title = Column(Text, default="", nullable=False)
    content_type = Column(String, default="text/markdown", nullable=False)
    content = Column(Text, default="", nullable=False)
    structured = Column(JSON, default=dict)
    artifact_metadata = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    result = relationship("MissionResultRecord", back_populates="artifacts")


class MissionResultVersionRecord(Base):
    __tablename__ = "mission_result_versions"

    version_id = Column(String, primary_key=True)
    mission_result_id = Column(String, ForeignKey("mission_results.mission_result_id", ondelete="CASCADE"), nullable=False, index=True)
    mission_id = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=False)
    reason = Column(Text, default="", nullable=False)
    snapshot = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    result = relationship("MissionResultRecord", back_populates="versions")
