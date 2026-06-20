import os
import time
import json
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.db import HeuristicRecord, FailureRecord
from app.replay.screenshot_store import ScreenshotStore
from app.replay.timeline_service import TimelineService
from app.vision.vision_policy import VisionTriggerPolicy
from app.vision.vision_service import VisionService
from app.failure_engine.classifier import FailureClassifier
from app.failure_engine.remedy_db import RemedyDatabase
from app.recovery.recovery_orchestrator import RecoveryOrchestrator
from app.memory.learning_layer import LearningLayer

# Test Database setup for learning layer testing
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_screenshot_store(tmp_path):
    # Set up temp screenshot store
    store = ScreenshotStore(storage_dir=str(tmp_path))
    
    # Base64 string for a blank 1x1 image or dummy string
    dummy_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    file_path = store.save_screenshot("session_123", 1, dummy_b64)
    
    assert os.path.exists(file_path)
    assert file_path.endswith(".webp")
    
    # Save a second one and simulate that it's old (older than 7 days)
    file_path_old = store.save_screenshot("session_123", 2, dummy_b64)
    assert os.path.exists(file_path_old)
    
    # Force modify mtime to 8 days ago
    eight_days_ago = time.time() - (8 * 24 * 3600)
    os.utime(file_path_old, (eight_days_ago, eight_days_ago))
    
    # Run cleanup
    cleaned_count = store.run_cleanup_job()
    assert cleaned_count == 1
    assert not os.path.exists(file_path_old)
    assert os.path.exists(file_path)


def test_vision_trigger_policy():
    # 1. Skip vision if DOM success and high confidence
    assert VisionTriggerPolicy.should_trigger_vision(dom_success=True, is_high_risk=False, confidence=0.95) is False
    
    # 2. Force vision if high risk (even with DOM success)
    assert VisionTriggerPolicy.should_trigger_vision(dom_success=True, is_high_risk=True, confidence=0.95) is True
    
    # 3. Trigger vision if DOM fails
    assert VisionTriggerPolicy.should_trigger_vision(dom_success=False, is_high_risk=False, confidence=0.95) is True
    
    # 4. Trigger vision if confidence is low
    assert VisionTriggerPolicy.should_trigger_vision(dom_success=True, is_high_risk=False, confidence=0.65) is True


def test_timeline_service(tmp_path):
    session_id = "test_timeline_session"
    timeline = TimelineService(session_id=session_id, storage_dir=str(tmp_path))
    
    # Record first step
    step1 = timeline.record_step(
        step_number=1,
        action_type="click",
        value_used="selector: #search",
        state_before={"search_clicked": False},
        state_after={"search_clicked": True},
        screenshot_before="sc_1_before.webp",
        screenshot_after="sc_1_after.webp",
        success=True
    )
    
    assert step1.step_number == 1
    assert step1.action_type == "click"
    assert step1.success is True
    
    # Record second step (failure)
    step2 = timeline.record_step(
        step_number=2,
        action_type="validation",
        value_used="verify_flights_loaded",
        state_before={"search_clicked": True},
        state_after={"search_clicked": True},
        screenshot_before="sc_2_before.webp",
        screenshot_after="sc_2_after.webp",
        success=False
    )
    
    assert len(timeline.steps) == 2
    assert timeline.steps[1].success is False
    
    # Verify file is written
    assert os.path.exists(timeline.file_path)
    
    # Reload and verify persistence
    timeline_reload = TimelineService(session_id=session_id, storage_dir=str(tmp_path))
    assert len(timeline_reload.steps) == 2
    assert timeline_reload.steps[0].action_type == "click"
    assert timeline_reload.steps[1].success is False


def test_failure_classifier_and_remedy():
    # 1. Test execution result classification
    assert FailureClassifier.classify_failure("Element not found: #submit") == "SELECTOR_STALE"
    assert FailureClassifier.classify_failure("Timeout waiting for response") == "RESULTS_NOT_LOADED"
    
    # 2. Test validator failure classification
    assert FailureClassifier.classify_failure("validator_failed", "verify_chats_loaded") == "RESULTS_NOT_LOADED"
    assert FailureClassifier.classify_failure("validator_failed", "verify_modal_closed") == "POPUP_BLOCKING"
    assert FailureClassifier.classify_failure("validator_failed", "verify_custom_err") == "VALIDATION_MISMATCH_VERIFY_CUSTOM_ERR"
    
    # 3. Test Remedy database lookups
    remedy_stale = RemedyDatabase.get_remedy("SELECTOR_STALE")
    assert remedy_stale["strategy"] == "recalculate_selectors"
    assert remedy_stale["action"] == "wait"
    
    remedy_popup = RemedyDatabase.get_remedy("POPUP_BLOCKING")
    assert remedy_popup["strategy"] == "dismiss_overlay"
    assert remedy_popup["selector"] == "body"
    
    remedy_generic = RemedyDatabase.get_remedy("SOME_UNKNOWN_CODE")
    assert remedy_generic["strategy"] == "generic_retry"


def test_recovery_orchestrator():
    orchestrator = RecoveryOrchestrator(session_id="session_rec", max_retries=3)
    
    # Retry 0: should return remedy database strategy
    rec1 = orchestrator.generate_recovery_action("SELECTOR_STALE", retry_count=0)
    assert rec1["action_type"] == "wait"
    assert rec1["value"] == "3000"
    
    # Retry 1: popup blocking strategy
    rec2 = orchestrator.generate_recovery_action("POPUP_BLOCKING", retry_count=1)
    assert rec2["action_type"] == "click"
    assert rec2["target_selector"] == "body"
    
    # Retry 3: exceeded max retries (3) -> Escalate to User Intervention
    rec3 = orchestrator.generate_recovery_action("SELECTOR_STALE", retry_count=3)
    assert rec3["action_type"] == "user_intervention"
    assert "complete this step manually" in rec3["message"]


def test_learning_layer(db_session):
    learning = LearningLayer(db=db_session)
    
    # Initial attempt record
    learning.record_attempt("makemytrip.com", "SELECTOR_STALE", "recalculate_selectors", success=True)
    rate = learning.get_remedy_success_rate("makemytrip.com", "SELECTOR_STALE", "recalculate_selectors")
    assert rate == 1.0
    
    # Add a failure attempt
    learning.record_attempt("makemytrip.com", "SELECTOR_STALE", "recalculate_selectors", success=False)
    rate = learning.get_remedy_success_rate("makemytrip.com", "SELECTOR_STALE", "recalculate_selectors")
    # should be 1/2 = 0.5
    assert rate == 0.5
    
    # Record another failure to test temporal decay on subsequent attempt
    learning.record_attempt("makemytrip.com", "SELECTOR_STALE", "recalculate_selectors", success=False)
    
    record = db_session.query(HeuristicRecord).first()
    assert record.attempt_count > 1
    assert record.success_count < 2


@patch("google.genai.Client")
def test_vision_service_mock(mock_client_class):
    # Setup mock response
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.text = '{"condition_met": true, "reasoning": "The flight results list is clearly visible in the screenshot.", "confidence": 0.95}'
    mock_client.models.generate_content.return_value = mock_response
    
    service = VisionService()
    # Ensure api_key check is bypassed
    service.api_key = "dummy_key"
    
    dummy_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    result = service.verify_visually(dummy_b64, "Is the flight search results list visible?")
    
    assert result["condition_met"] is True
    assert result["confidence"] == 0.95
    assert "visible" in result["reasoning"]
