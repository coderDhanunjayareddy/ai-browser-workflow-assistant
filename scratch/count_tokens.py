import os
import json
import sys
from google import genai

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        try:
            with open("backend/.env", "r") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        api_key = line.split("=")[1].strip()
                        break
        except Exception:
            pass

    if not api_key:
        print("GEMINI_API_KEY not found!")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    with open("scratch/failed_payload.json", "r", encoding="utf-8") as f:
        payload = json.load(f)

    sys.path.insert(0, "c:/Work/AI_Browser_Assist/backend")
    from app.services.context_service import format_page_context, format_prior_steps
    from app.schemas.request import PageContext, PriorStep
    
    ctx = PageContext(**payload["page_context"])
    prior_steps = [PriorStep(**p) for p in payload["prior_steps"]]
    
    page_context_text = format_page_context(ctx)
    prior_steps_text = format_prior_steps(prior_steps)
    
    msg = f"TASK: {payload['task']}\n\nPAGE CONTEXT:\n{page_context_text}"
    if payload.get("supplemental_context"):
        msg += f"\n\nSUPPLEMENTAL CONTEXT:\n{payload['supplemental_context'][:3000]}"
    if prior_steps_text:
        msg += f"\n\n{prior_steps_text}"

    from app.services.ai_service import SYSTEM_PROMPT

    print("Counting tokens using gemini-2.5-flash...")
    # Count tokens of contents
    res_contents = client.models.count_tokens(
        model="gemini-2.5-flash",
        contents=msg
    )
    print("Contents token count:", res_contents.total_tokens)

    # Count tokens of system prompt
    res_system = client.models.count_tokens(
        model="gemini-2.5-flash",
        contents=SYSTEM_PROMPT
    )
    print("System prompt token count:", res_system.total_tokens)
    print("Total input tokens:", res_contents.total_tokens + res_system.total_tokens)

if __name__ == "__main__":
    main()
