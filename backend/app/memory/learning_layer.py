import math
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.db import HeuristicRecord

logger = logging.getLogger(__name__)

class LearningLayer:
    """
    Component 9.5: Learning Layer
    Maintains selector success statistics and applies exponential temporal decay.
    """
    def __init__(self, db: Session):
        self.db = db
        self.decay_constant = 0.05  # lambda = 0.05 for temporal decay

    def record_attempt(self, domain: str, error_code: str, remedy_code: str, success: bool) -> None:
        """
        Updates selector statistics, applying a decay factor to older stats.
        """
        record = self.db.query(HeuristicRecord).filter(
            HeuristicRecord.site_domain == domain,
            HeuristicRecord.failure_code == error_code,
            HeuristicRecord.remedy_code == remedy_code
        ).first()

        if not record:
            record = HeuristicRecord(
                site_domain=domain,
                failure_code=error_code,
                remedy_code=remedy_code,
                success_count=1 if success else 0,
                attempt_count=1
            )
            self.db.add(record)
        else:
            # Apply decay factor: old stats are scaled down
            decay = math.exp(-self.decay_constant)
            
            record.success_count = round(record.success_count * decay) + (1 if success else 0)
            record.attempt_count = round(record.attempt_count * decay) + 1
            
        self.db.commit()
        logger.info(f"Updated Learning statistics for {domain} ({error_code} -> {remedy_code}): success_count={record.success_count}, attempt_count={record.attempt_count}")

    def get_remedy_success_rate(self, domain: str, error_code: str, remedy_code: str) -> float:
        record = self.db.query(HeuristicRecord).filter(
            HeuristicRecord.site_domain == domain,
            HeuristicRecord.failure_code == error_code,
            HeuristicRecord.remedy_code == remedy_code
        ).first()
        
        if not record or record.attempt_count == 0:
            return 1.0
            
        return record.success_count / record.attempt_count
