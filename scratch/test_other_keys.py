import os
import json
import sys
from google import genai
from google.genai import types

def main():
    keys = []
    with open("backend/candidate_gemini_keys.txt", "r") as f:
        for line in f:
            k = line.strip()
            if k:
                keys.append(k)

    print(f"Found {len(keys)} candidate keys to test.")

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

    for idx, key in enumerate(keys):
        print(f"\n--- Testing Key {idx+1}: {key[:10]}... ---")
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=msg,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    max_output_tokens=4096,
                    temperature=0,
                ),
            )
            print(f"Success! Output Length: {len(response.text)} chars.")
            if response.candidates:
                print(f"Finish Reason: {response.candidates[0].finish_reason}")
            else:
                print("No candidates.")
            
            # Print a snippet to verify completeness
            print("Preview ending:", repr(response.text[-80:]))
        except Exception as e:
            print(f"Failed with key {idx+1}: {e}")

if __name__ == "__main__":
    main()
