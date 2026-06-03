import sys
import os
import json
import time

sys.path.insert(0, "c:/Work/AI_Browser_Assist/backend")

# Set up environment variables
try:
    with open("backend/.env", "r") as f:
        for line in f:
            if line.startswith("GEMINI_API_KEY="):
                os.environ["GEMINI_API_KEY"] = line.split("=")[1].strip()
            if line.startswith("GEMINI_MODEL="):
                os.environ["GEMINI_MODEL"] = line.split("=")[1].strip()
except Exception as e:
    print("Error reading .env:", e)

from app.schemas.request import PageContext
from app.services import ai_service
from app.core.config import settings

def main():
    print(f"GEMINI_API_KEY configured: {bool(settings.gemini_api_key)}")
    print(f"GEMINI_MODEL configured: {settings.gemini_model}")
    
    task = "acting as Product Intelligence Extraction Agent, extract product details"
    
    ctx_data = {
        "url": "https://www.sony.co.in/electronics/headband-headphones/wh-1000xm5",
        "title": "WH-1000XM5 Wireless Industry Leading Noise Cancelling Headphones | Sony IN",
        "metadata": {
            "site_name": "Sony India"
        },
        "headings": ["Sony WH-1000XM5"],
        "interactive_elements": [],
        "content_blocks": [],
        "selected_text": "",
        "visible_text": "Sony WH-1000XM5. Price Rs. 29,990.",
        "images": [
            "https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png"
        ]
    }
    
    ctx = PageContext(**ctx_data)
    
    print("\nCalling ai_service.analyze directly...")
    start_time = time.time()
    try:
        response = ai_service.analyze(
            session_id="direct-test-session",
            task=task,
            page_context=ctx,
            prior_steps=[],
            supplemental_context=""
        )
        duration = time.time() - start_time
        print(f"\nCompleted in {duration:.2f} seconds.")
        print("\nResponse:")
        print("====================================")
        print("Analysis:", response.analysis[:200] + "...")
        print("Suggested actions:", response.suggested_actions)
        print("====================================")
    except Exception as e:
        print("\nFailed with exception:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
