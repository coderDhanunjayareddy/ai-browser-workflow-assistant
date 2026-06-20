import os
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class FileWorkflowEngine:
    """
    Gap 2: File Upload & Download Engine
    Validates uploaded files and polls directories for completed downloads.
    """
    @staticmethod
    def verify_upload(file_path: str) -> bool:
        """
        Confirms the target upload file exists and has non-zero size.
        """
        exists = os.path.exists(file_path) and os.path.getsize(file_path) > 0
        logger.info(f"Verifying upload for {file_path}: result={exists}")
        return exists

    @staticmethod
    def wait_for_download(download_dir: str, file_pattern: str, timeout: int = 30) -> Optional[str]:
        """
        Polls target directory to check for download complete (ignoring partial temp files).
        """
        logger.info(f"Monitoring downloads in {download_dir} matching '{file_pattern}'")
        start_time = time.time()
        while time.time() - start_time < timeout:
            if not os.path.exists(download_dir):
                time.sleep(1)
                continue
            for filename in os.listdir(download_dir):
                if filename.endswith(".crdownload") or filename.endswith(".tmp"):
                    continue
                if file_pattern in filename:
                    full_path = os.path.join(download_dir, filename)
                    logger.info(f"Download complete: {full_path}")
                    return full_path
            time.sleep(1)
        logger.warning(f"Download timeout reached for pattern '{file_pattern}'")
        return None
        # Download monitoring logic goes here.
