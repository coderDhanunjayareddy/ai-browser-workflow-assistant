import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class TimelineStep:
    def __init__(self, step_number: int, action_type: str, value_used: str, state_before: Dict[str, Any], state_after: Dict[str, Any], screenshot_before: str = "", screenshot_after: str = "", success: bool = True):
        self.step_number = step_number
        self.action_type = action_type
        self.value_used = value_used
        self.state_before = state_before
        self.state_after = state_after
        self.screenshot_before = screenshot_before
        self.screenshot_after = screenshot_after
        self.success = success
        self.timestamp = datetime.utcnow().isoformat()

class TimelineService:
    """
    Component 12: Timeline Service for Workflow Replay
    Constructs and persists chronological steps and state audits.
    """
    def __init__(self, session_id: str, storage_dir: str = "c:/Work/AI_Browser_Assist/screenshots"):
        self.session_id = session_id
        self.storage_dir = storage_dir
        self.file_path = os.path.join(storage_dir, f"{session_id}_timeline.json")
        self.steps: List[TimelineStep] = []
        self._load_timeline()

    def _load_timeline(self) -> None:
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        step = TimelineStep(
                            step_number=item.get("step_number"),
                            action_type=item.get("action_type"),
                            value_used=item.get("value_used"),
                            state_before=item.get("state_before"),
                            state_after=item.get("state_after"),
                            screenshot_before=item.get("screenshot_before"),
                            screenshot_after=item.get("screenshot_after"),
                            success=item.get("success")
                        )
                        if "timestamp" in item:
                            step.timestamp = item["timestamp"]
                        self.steps.append(step)
                logger.info(f"Loaded {len(self.steps)} timeline steps for session {self.session_id}")
            except Exception as e:
                logger.error(f"Failed to load timeline for {self.session_id}: {e}")

    def _save_timeline(self) -> None:
        os.makedirs(self.storage_dir, exist_ok=True)
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump([step.__dict__ for step in self.steps], f, indent=2)
            logger.info(f"Saved timeline steps to {self.file_path}")
        except Exception as e:
            logger.error(f"Failed to save timeline for {self.session_id}: {e}")

    def record_step(self, step_number: int, action_type: str, value_used: str, state_before: Dict[str, Any], state_after: Dict[str, Any], screenshot_before: str = "", screenshot_after: str = "", success: bool = True) -> TimelineStep:
        step = TimelineStep(
            step_number=step_number,
            action_type=action_type,
            value_used=value_used,
            state_before=state_before,
            state_after=state_after,
            screenshot_before=screenshot_before,
            screenshot_after=screenshot_after,
            success=success
        )
        self.steps.append(step)
        logger.info(f"Recorded timeline step {step_number} for session {self.session_id}")
        self._save_timeline()
        return step

    def get_timeline(self) -> List[Dict[str, Any]]:
        return [step.__dict__ for step in self.steps]
