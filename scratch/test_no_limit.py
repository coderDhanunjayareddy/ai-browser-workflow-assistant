import os
import json
import sys
from google import genai
from google.genai import types

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

    print("Calling Gemini model gemini-2.5-flash with NO max_output_tokens configured...")
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=msg,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
            ),
        )
        
        output_data = {
            "text": response.text,
            "candidates": []
        }
        if response.candidates:
            for idx, candidate in enumerate(response.candidates):
                output_data["candidates"].append({
                    "finish_reason": str(candidate.finish_reason),
                    "safety_ratings": []
                })
        
        with open("scratch/gemini_no_limit_response.json", "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
            
        print("Success! Details written to scratch/gemini_no_limit_response.json")
    except Exception as e:
        print("API Call failed:", e)

if __name__ == "__main__":
    main()
