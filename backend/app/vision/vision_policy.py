import logging

logger = logging.getLogger(__name__)

class VisionTriggerPolicy:
    """
    Gap 4: Vision Cost Optimization Policy
    Decides when to capture and submit screenshots to Gemini models to minimize token costs.
    """
    @staticmethod
    def should_trigger_vision(dom_success: bool, is_high_risk: bool, confidence: float) -> bool:
        # 1. Skip vision if DOM validator reports high confidence success
        if dom_success and confidence >= 0.9 and not is_high_risk:
            logger.info("DOM validation succeeded with high confidence. Skipping vision to optimize costs.")
            return False
            
        # 2. Force vision verification for high risk steps (payments, send actions)
        if is_high_risk:
            logger.info("Action flagged as high-risk. Forcing vision verification.")
            return True
            
        # 3. Trigger vision if DOM validation is uncertain or fails
        if not dom_success or confidence < 0.7:
            logger.info("DOM validation failed or has low confidence. Triggering vision verification.")
            return True
            
        return False
