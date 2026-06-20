import logging
import os
import base64
import json
from typing import Dict, Any, Optional
from google import genai
from google.genai import types

from app.core.config import settings

logger = logging.getLogger(__name__)

class VisionService:
    """
    Component 4: Vision Engine
    Executes screenshot-based visual verification using Gemini-only models.
    """
    def __init__(self):
        self.api_key = settings.gemini_api_key
        self.model = settings.gemini_model

    def verify_visually(self, screenshot_base64: str, target_question: str) -> Dict[str, Any]:
        """
        Submits screenshot bytes to Gemini for visual condition verification.
        """
        logger.info(f"Running visual verification question: {target_question}")
        if os.environ.get("MOCK_VISION") == "true":
            logger.info("Mock Vision mode enabled. Returning condition_met=True.")
            return {"condition_met": True, "reasoning": "Mock vision success", "confidence": 1.0}
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not configured. Skipping visual check.")
            return {"condition_met": False, "reasoning": "Gemini key missing", "confidence": 0.0}

        try:
            # Decode base64 screenshot
            if "," in screenshot_base64:
                screenshot_base64 = screenshot_base64.split(",")[1]
            img_bytes = base64.b64decode(screenshot_base64)
            
            client = genai.Client(api_key=self.api_key)
            contents = [
                types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                types.Part.from_text(text=(
                    f"Analyze this screenshot and answer this verification check:\n"
                    f"Question: {target_question}\n\n"
                    f"Return a valid JSON object in the following format:\n"
                    f"{{\n"
                    f"  \"condition_met\": true/false,\n"
                    f"  \"reasoning\": \"1-2 sentences explanation of what is visually visible.\",\n"
                    f"  \"confidence\": 0.0 to 1.0\n"
                    f"}}\n"
                ))
            ]

            response = client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0
                )
            )

            result_text = response.text or "{}"
            data = json.loads(result_text)
            logger.info(f"Visual check result: {data}")
            return data
        except Exception as e:
            logger.error(f"Multimodal vision query failed: {e}")
            return {"condition_met": False, "reasoning": f"Vision error: {str(e)}", "confidence": 0.0}
