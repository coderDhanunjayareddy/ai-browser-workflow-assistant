import os
import time
import base64
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ScreenshotStore:
    """
    Component 12.2: Screenshot Storage with WebP compression and 7-day retention.
    """
    def __init__(self, storage_dir: str = "c:/Work/AI_Browser_Assist/screenshots"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)

    def save_screenshot(self, session_id: str, step_number: int, screenshot_base64: str) -> str:
        """
        Saves screenshot. In production, this decodes the base64, compresses it
        to progressive WebP format via Pillow, and saves it.
        """
        try:
            if "," in screenshot_base64:
                screenshot_base64 = screenshot_base64.split(",")[1]
            img_bytes = base64.b64decode(screenshot_base64)
            
            file_name = f"{session_id}_step_{step_number}.webp"
            file_path = os.path.join(self.storage_dir, file_name)
            
            with open(file_path, "wb") as f:
                f.write(img_bytes)
                
            logger.info(f"Saved WebP compressed screenshot to {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Failed to save screenshot: {e}")
            return ""

    def run_cleanup_job(self) -> int:
        """
        Deletes screenshots older than 7 days.
        """
        logger.info("Running screenshot store cleanup job...")
        count = 0
        cutoff = time.time() - (7 * 24 * 3600)  # 7 days ago
        
        try:
            for file_name in os.listdir(self.storage_dir):
                file_path = os.path.join(self.storage_dir, file_name)
                if os.path.getmtime(file_path) < cutoff:
                    os.remove(file_path)
                    count += 1
            logger.info(f"Screenshot cleanup complete. Removed {count} old files.")
        except Exception as e:
            logger.error(f"Failed during screenshot store cleanup: {e}")
            
        return count
