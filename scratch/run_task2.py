import os
import sys
import json
import uuid
import requests
from playwright.sync_api import sync_playwright

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        try:
            print(text.encode('ascii', errors='replace').decode('ascii'))
        except Exception:
            pass

def main():
    safe_print("Loading compiled content scripts...")
    
    # Read and clean extractor.js
    extractor_path = "c:/Work/AI_Browser_Assist/scratch/content/extractor.js"
    with open(extractor_path, "r", encoding="utf-8") as f:
        extractor_js = f.read()
    extractor_js = extractor_js.replace("export function", "function")
    
    # Read and clean executor.js
    executor_path = "c:/Work/AI_Browser_Assist/scratch/content/executor.js"
    with open(executor_path, "r", encoding="utf-8") as f:
        executor_js = f.read()
    executor_js = executor_js.replace("export async function", "async function")
    
    task = (
        "Search for 'wireless headphones under 2000' on Flipkart, "
        "then do the same search on Amazon, "
        "compare the top 3 results from both sites, "
        "and add the cheapest one with the highest rating to the cart on whichever site has it"
    )
    
    session_id = str(uuid.uuid4())
    prior_steps = []
    
    # Ensure screenshots dir exists
    screenshots_dir = "c:/Work/AI_Browser_Assist/screenshots"
    os.makedirs(screenshots_dir, exist_ok=True)
    
    safe_print("Launching Chromium via Playwright...")
    with sync_playwright() as p:
        # Launch Chrome using the profile to keep settings/session
        browser = p.chromium.launch_persistent_context(
            user_data_dir="c:/Work/AI_Browser_Assist/chrome-profile",
            headless=False,
            no_viewport=False,
            viewport={"width": 1280, "height": 800}
        )
        
        page = browser.pages[0] if browser.pages else browser.new_page()
        
        # Navigate to a blank page to start
        safe_print("Navigating to about:blank to begin workflow...")
        page.goto("about:blank")
        page.wait_for_timeout(2000)
        
        step_number = 1
        max_steps = 20
        
        while step_number <= max_steps:
            safe_print(f"\n--- STEP {step_number} ---")
            
            # Ensure we are always focusing on the latest opened page/tab
            page = browser.pages[-1]
            
            # 1. Extract context
            safe_print("Extracting page context...")
            extractor_code = extractor_js + "\nextractPageContext();"
            try:
                context = page.evaluate(extractor_code)
            except Exception as e:
                safe_print(f"Error evaluating extractor: {e}")
                # Sometimes page is navigating, wait and retry once
                page.wait_for_timeout(3000)
                context = page.evaluate(extractor_code)
                
            safe_print(f"Current URL: {context['url']}")
            safe_print(f"Current Title: {context['title']}")
            
            # 2. Call backend analyze API
            payload = {
                "session_id": session_id,
                "task": task,
                "page_context": context,
                "prior_steps": prior_steps,
                "supplemental_context": ""
            }
            
            safe_print("Sending context to backend for analysis...")
            try:
                res = requests.post("http://localhost:8000/analyze", json=payload)
                res.raise_for_status()
                res_data = res.json()
                
                # Check for fallback failure
                if res_data.get("clarification_question") == "The AI response was invalid. Click Continue to retry from the current page.":
                    safe_print("Detected fallback parse failure! Saving failed payload to scratch/failed_payload.json...")
                    with open("c:/Work/AI_Browser_Assist/scratch/failed_payload.json", "w", encoding="utf-8") as f:
                        json.dump(payload, f, indent=2)
                    break
            except Exception as e:
                safe_print(f"Backend request failed: {e}")
                break
                
            analysis_text = res_data.get("analysis", "")
            safe_print(f"Analysis: {analysis_text}")
            
            if res_data.get("clarification_question"):
                safe_print(f"CLARIFICATION REQUIRED: {res_data['clarification_question']}")
                # We do not expect clarification questions in this benchmark task, break if so
                break
                
            suggested_actions = res_data.get("suggested_actions", [])
            if not suggested_actions:
                safe_print("No actions suggested. Task is complete!")
                break
                
            safe_print(f"Suggested {len(suggested_actions)} actions:")
            for act in suggested_actions:
                safe_print(f"- {act['action_type'].upper()}: {act['description']} (Selector: {act['target_selector']}, Value: {act['value']})")
                
            # 3. Take screenshot before executing actions
            screenshot_path = os.path.join(screenshots_dir, f"step_{step_number}_browser.png")
            page.screenshot(path=screenshot_path)
            safe_print(f"Screenshot saved to {screenshot_path}")
            
            # 4. Execute actions
            for action in suggested_actions:
                action_type = action["action_type"]
                desc = action["description"]
                target = action["target_selector"]
                val = action["value"]
                
                safe_print(f"Executing action: {desc}")
                
                if action_type == "navigate":
                    safe_print(f"Navigating to: {val}")
                    try:
                        page.goto(val, timeout=30000)
                        exec_result = "success"
                    except Exception as e:
                        safe_print(f"Navigation failed: {e}")
                        exec_result = f"navigation failed: {str(e)}"
                else:
                    executor_code = executor_js + f"\nexecuteAction({json.dumps(action)});"
                    try:
                        res_action = page.evaluate(executor_code)
                        safe_print(f"Result: {res_action}")
                        if res_action.get("success"):
                            exec_result = "success"
                        else:
                            exec_result = f"failed: {res_action.get('message')}"
                    except Exception as e:
                        safe_print(f"Action execution error: {e}")
                        exec_result = f"execution error: {str(e)}"
                        
                # Record prior step
                prior_steps.append({
                    "action_type": action_type,
                    "description": desc,
                    "target_selector": target,
                    "value": val,
                    "execution_result": exec_result,
                    "page_analysis": res_data.get("analysis"),
                    "page_url": context["url"],
                    "page_title": context["title"],
                    "page_metadata": context["metadata"]
                })
                
                # Settle down
                page.wait_for_timeout(3000)
                
            step_number += 1
            
        safe_print("\nWorkflow completed.")
        browser.close()

if __name__ == "__main__":
    main()
