import os
import sys
import json
import uuid
import time
import requests
import argparse
from playwright.sync_api import sync_playwright

TASKS = [
    {
        "id": 1,
        "name": "TASK 1: YouTube Search + Gmail Compose + Google Doc",
        "prompt": "Go to YouTube, search for 'React tutorial for beginners', open the top video, copy the video title and channel name, then open Gmail and compose a new email to my friend saying 'Check out this tutorial: [video title] by [channel name]', and also save the video link to a new Google Doc called 'Learning Resources'"
    },
    {
        "id": 2,
        "name": "TASK 2: Price Comparison (Flipkart vs Amazon)",
        "prompt": "Search for 'wireless headphones under 2000' on Flipkart, then do the same search on Amazon, compare the top 3 results from both sites, and add the cheapest one with the highest rating to the cart on whichever site has it"
    },
    {
        "id": 3,
        "name": "TASK 3: LinkedIn Job Search & Extract",
        "prompt": "Go to LinkedIn, search for 'React developer jobs in Hyderabad', filter by 'Remote' and 'Entry level', open the top 5 job postings, extract the company name and salary range for each, and create a summary list in a new tab"
    },
    {
        "id": 4,
        "name": "TASK 4: Movie Ticket Booking",
        "prompt": "Book a ticket for the movie 'Jawan' today at 7 PM at PVR Gachibowli Hyderabad, select 2 seats in the middle row, and navigate to the payment page (don't pay)"
    },
    {
        "id": 5,
        "name": "TASK 5: Instagram NASA Download + Canva Story Draft",
        "prompt": "Go to Instagram profile of 'nasa', download the 3 most recent posts, then open Canva and create a new Instagram story using the first image, add text saying 'Space Alert' at the top, and save it as a draft"
    },
    {
        "id": 6,
        "name": "TASK 6: Google News AI Digest + Email Self",
        "prompt": "Search for 'AI browser assistants news 2026' on Google News, open the top 3 articles, summarize each article in 2 sentences, compile all summaries into one document, and email it to myself with subject 'AI Research Digest'"
    },
    {
        "id": 7,
        "name": "TASK 7: Zomato Biryani Order",
        "prompt": "Go to Zomato, search for 'biryani' near Hitech City Hyderabad, filter by rating 4+, sort by delivery time, open the top restaurant's page, add 2 vegetable biryani to cart, and proceed to checkout page"
    },
    {
        "id": 8,
        "name": "TASK 8: MakeMyTrip Flight + Hotel Search + Google Doc",
        "prompt": "Search flights from Hyderabad to Goa on MakeMyTrip for next Friday, find the cheapest direct flight under 5000, then search for hotels in Baga Beach for 2 nights under 3000 per night, and create a Google Doc with flight details and hotel name"
    },
    {
        "id": 9,
        "name": "TASK 9: GitHub Template Search & README Extraction",
        "prompt": "Go to GitHub, search for 'React TypeScript starter template', open the top 3 repositories, check their star count and last updated date, copy the installation command from each README, and save them to a new GitHub Gist"
    },
    {
        "id": 10,
        "name": "TASK 10: iPhone 15 Amazon/Flipkart/Croma Compare + Google Sheet",
        "prompt": "Search for 'iPhone 15' on Amazon, note the price, then search on Flipkart and Croma, compare all three prices, check if there's an 'Add to Cart' button available on all sites, and open a new tab with a Google Sheet pre-filled with the comparison table (product, site, price, in-stock status)"
    }
]

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        try:
            print(text.encode('ascii', errors='replace').decode('ascii'))
        except Exception:
            pass

def inject_pause_banner(page, reason, url):
    banner_js = f"""
    (() => {{
        // Remove existing if any
        const existing = document.getElementById('automation-pause-banner');
        if (existing) existing.remove();

        const banner = document.createElement('div');
        banner.id = 'automation-pause-banner';
        banner.style.position = 'fixed';
        banner.style.top = '15px';
        banner.style.left = '50%';
        banner.style.transform = 'translateX(-50%)';
        banner.style.backgroundColor = '#e74c3c';
        banner.style.color = '#ffffff';
        banner.style.padding = '16px 28px';
        banner.style.borderRadius = '10px';
        banner.style.boxShadow = '0 6px 20px rgba(0,0,0,0.25)';
        banner.style.zIndex = '999999';
        banner.style.fontSize = '16px';
        banner.style.fontWeight = 'bold';
        banner.style.fontFamily = 'system-ui, -apple-system, sans-serif';
        banner.style.textAlign = 'center';
        banner.style.border = '2px solid #ffffff';
        
        // Build DOM programmatically to bypass Trusted Types innerHTML policy
        const titleDiv = document.createElement('div');
        titleDiv.style.marginBottom = '8px';
        titleDiv.style.fontSize = '18px';
        titleDiv.textContent = '⚠️ ACTION REQUIRED';
        banner.appendChild(titleDiv);

        const reasonDiv = document.createElement('div');
        reasonDiv.style.marginBottom = '6px';
        reasonDiv.style.fontWeight = 'normal';
        reasonDiv.textContent = 'Reason: ';
        const reasonStrong = document.createElement('strong');
        reasonStrong.textContent = {json.dumps(reason)};
        reasonDiv.appendChild(reasonStrong);
        banner.appendChild(reasonDiv);

        const instructionsDiv = document.createElement('div');
        instructionsDiv.style.fontSize = '14px';
        instructionsDiv.style.fontWeight = 'normal';
        instructionsDiv.style.opacity = '0.9';
        instructionsDiv.textContent = 'Please complete this step manually in the browser.';
        banner.appendChild(instructionsDiv);

        const resumeDiv = document.createElement('div');
        resumeDiv.style.fontSize = '14px';
        resumeDiv.style.marginTop = '8px';
        resumeDiv.style.backgroundColor = 'rgba(255,255,255,0.2)';
        resumeDiv.style.padding = '4px 8px';
        resumeDiv.style.borderRadius = '4px';
        resumeDiv.style.fontWeight = 'normal';
        resumeDiv.textContent = 'Press ENTER in the terminal window to continue automation...';
        banner.appendChild(resumeDiv);

        document.body.appendChild(banner);
    }})();
    """
    try:
        page.evaluate(banner_js)
    except Exception as e:
        safe_print(f"Could not inject banner to browser page: {e}")

def remove_pause_banner(page):
    remove_js = """
    (() => {
        const banner = document.getElementById('automation-pause-banner');
        if (banner) banner.remove();
    })();
    """
    try:
        page.evaluate(remove_js)
    except Exception:
        pass

def run_single_task(browser_context, task_info, max_steps=50):
    task_id = task_info["id"]
    task_name = task_info["name"]
    prompt = task_info["prompt"]
    
    safe_print(f"\n==================================================================")
    safe_print(f"RUNNING {task_name}")
    safe_print(f"Prompt: {prompt}")
    safe_print(f"==================================================================")
    
    # Read content scripts
    extractor_path = "c:/Work/AI_Browser_Assist/scratch/content/extractor.js"
    with open(extractor_path, "r", encoding="utf-8") as f:
        extractor_js = f.read().replace("export function", "function")
        
    executor_path = "c:/Work/AI_Browser_Assist/scratch/content/executor.js"
    with open(executor_path, "r", encoding="utf-8") as f:
        executor_js = f.read().replace("export async function", "async function")
        
    # Start clean page
    page = browser_context.new_page()
    page.goto("about:blank")
    page.wait_for_timeout(1000)
    
    session_id = f"dry-run-task-{task_id}-{uuid.uuid4().hex[:8]}"
    prior_steps = []
    
    # Screenshots directory
    screenshots_dir = f"c:/Work/AI_Browser_Assist/screenshots/task_{task_id}"
    os.makedirs(screenshots_dir, exist_ok=True)
    
    status = "SUCCESS"
    reason = "Finished successfully (no further actions suggested)."
    failure_step = None
    
    step = 1
    while step <= max_steps:
        safe_print(f"\n--- {task_name} | Step {step} ---")
        
        # Focus latest page
        if len(browser_context.pages) > 0:
            page = browser_context.pages[-1]
            
        # 1. Extract context
        safe_print("Extracting page context...")
        extractor_code = extractor_js + "\nextractPageContext();"
        try:
            context = page.evaluate(extractor_code)
        except Exception as e:
            safe_print(f"Error evaluating extractor (navigating?): {e}")
            page.wait_for_timeout(3000)
            try:
                context = page.evaluate(extractor_code)
            except Exception as e2:
                status = "FAILED"
                failure_step = step
                reason = f"Context extraction error: {e2}"
                safe_print(f"Context extraction failed twice: {e2}")
                break
                
        url = context.get("url", "unknown")
        title = context.get("title", "unknown")
        safe_print(f"URL: {url}")
        safe_print(f"Title: {title}")
        
        # Detect Login Walls & CAPTCHAs before calling backend
        needs_pause = False
        pause_reason = ""
        
        if "accounts.google.com" in url.lower():
            safe_print("Google Account Sign-In page detected. Skipping Google login per user instruction.")
            status = "SKIPPED_GOOGLE_LOGIN"
            reason = "Google Account Login required but skipped per user instruction."
            break
        elif "linkedin.com/checkpoint/lg/login" in url.lower() or "linkedin.com/login" in url.lower():
            needs_pause = True
            pause_reason = "LinkedIn Login Required"
        elif "instagram.com/accounts/login" in url.lower() or "instagram.com/login" in url.lower():
            needs_pause = True
            pause_reason = "Instagram Login Required"
        elif "github.com/login" in url.lower():
            needs_pause = True
            pause_reason = "GitHub Login Required"
        elif "canva.com/login" in url.lower():
            needs_pause = True
            pause_reason = "Canva Login Required"
        elif "zomato.com/signin" in url.lower() or "zomato.com/login" in url.lower():
            needs_pause = True
            pause_reason = "Zomato Login/OTP Required"
        elif "captcha" in url.lower() or "challenge" in url.lower() or page.query_selector("div.g-recaptcha") or page.query_selector("iframe[src*='recaptcha']"):
            needs_pause = True
            pause_reason = "CAPTCHA / Security Check Detected"
            
        # Canvas/SVG layout manual step overrides for specific tasks
        if task_id == 4 and "booking" in url.lower() and ("seat" in url.lower() or "layout" in url.lower()):
            # PVR seat selection is usually SVG/canvas
            needs_pause = True
            pause_reason = "Please select 2 seats in the middle row manually"
        elif task_id == 5 and "canva.com/design" in url.lower() and step >= 7:
            needs_pause = True
            pause_reason = "Please create the Canva story/add 'Space Alert' text manually"
            
        if needs_pause:
            safe_print(f"\n[ACTION REQUIRED] Pausing execution at: {url}")
            safe_print(f"Reason: {pause_reason}")
            
            # Inject on-screen visual banner to browser page
            inject_pause_banner(page, pause_reason, url)
            
            # Prompt developer/user in the terminal
            safe_print("Please complete this step manually in the browser window.")
            sys.stdout.flush()
            input("Once done, press ENTER in this terminal to resume automation...")
            
            # Remove banner after resuming
            remove_pause_banner(page)
            
            # Settle down and re-run this step with fresh context
            page.wait_for_timeout(2000)
            continue
            
        # 2. Call backend analyze
        payload = {
            "session_id": session_id,
            "task": prompt,
            "page_context": context,
            "prior_steps": prior_steps,
            "supplemental_context": ""
        }
        
        safe_print("Requesting next action from FastAPI analyze API...")
        sys.stdout.flush()
        try:
            res = requests.post("http://localhost:8000/analyze", json=payload, timeout=60.0)
            res.raise_for_status()
            res_data = res.json()
        except Exception as e:
            status = "FAILED"
            failure_step = step
            reason = f"FastAPI analyze API request failed: {e}"
            safe_print(f"API request failed: {e}")
            break
            
        # Check fallback parser failure
        if res_data.get("clarification_question") == "The AI response was invalid. Click Continue to retry from the current page.":
            status = "FAILED"
            failure_step = step
            reason = "Backend parser fallback failure (invalid JSON returned by AI)."
            safe_print("FastAPI returned fallback parse failure.")
            break
            
        analysis = res_data.get("analysis", "")
        clarification = res_data.get("clarification_question")
        suggested_actions = res_data.get("suggested_actions", [])
        
        safe_print(f"Analysis: {analysis}")
        
        # Check for AI-requested clarification (can be a login request or general question)
        if clarification:
            safe_print(f"\n[CLARIFICATION QUESTION FROM AI]: {clarification}")
            # If the clarification asks for credentials or logins, we trigger a pause
            if any(k in clarification.lower() for k in ["login", "signin", "password", "credentials", "otp", "code", "account"]):
                safe_print(f"[ACTION REQUIRED] Halted at: {url}")
                inject_pause_banner(page, clarification, url)
                input("Please complete this step manually in the browser. Once done, press ENTER to resume...")
                remove_pause_banner(page)
                page.wait_for_timeout(2000)
                continue
            else:
                # General clarification, prompt the user for input and send it back
                user_answer = input(f"Provide answer for: '{clarification}': ")
                prior_steps.append({
                    "action_type": "wait",
                    "description": f"User provided details: {user_answer}",
                    "target_selector": None,
                    "value": None,
                    "execution_result": "success",
                    "page_analysis": analysis,
                    "page_url": url,
                    "page_title": title,
                    "page_metadata": context.get("metadata", {})
                })
                # Add to inputs list for backend to see in supplemental context
                payload["supplemental_context"] += f"\nUser answer: {user_answer}"
                step += 1
                continue
            
        if not suggested_actions:
            safe_print("No suggested actions. Task complete!")
            break
            
        action = suggested_actions[0]
        action_type = action.get("action_type")
        desc = action.get("description", "")
        target = action.get("target_selector")
        val = action.get("value")
        
        safe_print(f"Suggested Action: {action_type.upper()} | {desc}")
        if target:
            safe_print(f"  Target Selector: {target}")
        if val:
            safe_print(f"  Value: {val}")
            
        # Check for infinite loop detection (same action repeatedly, alternating actions, or alternating URLs)
        if len(prior_steps) >= 3:
            # 1. Consecutive identical actions
            last_three_actions = [p["action_type"] + str(p["target_selector"]) + str(p["value"]) for p in prior_steps[-3:]]
            current_action_str = action_type + str(target) + str(val)
            if all(a == current_action_str for a in last_three_actions):
                status = "FAILED"
                failure_step = step
                reason = f"Infinite loop detected: suggested same action '{action_type}' on '{target}' repeatedly."
                safe_print("INFINITE LOOP DETECTED. Stopping task.")
                break

            # 2. Alternating action loops (e.g. Action_A -> Action_B -> Action_A -> Action_B -> Action_A)
            if len(prior_steps) >= 4:
                last_four_actions = [p["action_type"] + str(p["target_selector"]) + str(p["value"]) for p in prior_steps[-4:]]
                if last_four_actions[0] == last_four_actions[2] and last_four_actions[1] == last_four_actions[3] and current_action_str == last_four_actions[0]:
                    status = "FAILED"
                    failure_step = step
                    reason = f"Infinite loop detected: alternating between actions '{last_four_actions[0]}' and '{last_four_actions[1]}' repeatedly."
                    safe_print("INFINITE ALTERNATING LOOP DETECTED. Stopping task.")
                    break

            # 3. Alternating page URLs loops (e.g. URL_A -> URL_B -> URL_A -> URL_B -> URL_A)
            if len(prior_steps) >= 4:
                last_four_urls = [p["page_url"] for p in prior_steps[-4:]]
                if last_four_urls[0] == last_four_urls[2] and last_four_urls[1] == last_four_urls[3] and url == last_four_urls[0]:
                    status = "FAILED"
                    failure_step = step
                    reason = f"Infinite loop detected: alternating back-and-forth between URLs '{last_four_urls[0]}' and '{last_four_urls[1]}' repeatedly."
                    safe_print("INFINITE ALTERNATING URL LOOP DETECTED. Stopping task.")
                    break
                
        # Take screenshot
        screenshot_path = os.path.join(screenshots_dir, f"step_{step}_before_{action_type}.png")
        try:
            page.screenshot(path=screenshot_path)
            safe_print(f"Screenshot saved to {screenshot_path}")
        except Exception as e:
            safe_print(f"Could not take screenshot: {e}")
            
        # Execute Action
        exec_result = "success"
        if action_type == "navigate":
            safe_print(f"Executing: navigate to {val}")
            try:
                page.goto(val, timeout=30000)
            except Exception as e:
                safe_print(f"Navigation failed: {e}")
                exec_result = f"navigation failed: {str(e)}"
        else:
            safe_print(f"Executing: {action_type} via executor.js...")
            executor_code = executor_js + f"\nexecuteAction({json.dumps(action)});"
            try:
                res_action = page.evaluate(executor_code)
                safe_print(f"Execution Result: {res_action}")
                if res_action.get("success"):
                    exec_result = "success"
                else:
                    exec_result = f"failed: {res_action.get('message')}"
            except Exception as e:
                safe_print(f"Action execution error: {e}")
                exec_result = f"execution error: {str(e)}"
                
        # Record step
        prior_steps.append({
            "action_type": action_type,
            "description": desc,
            "target_selector": target,
            "value": val,
            "execution_result": exec_result,
            "page_analysis": analysis,
            "page_url": url,
            "page_title": title,
            "page_metadata": context.get("metadata", {})
        })
        
        # Settle wait
        page.wait_for_timeout(3000)
        step += 1
        
    else:
        # Loop finished without breaking
        status = "STOPPED_MAX_STEPS"
        failure_step = max_steps
        reason = f"Reached maximum dry run limit of {max_steps} steps."
        safe_print(f"Reached max steps limit ({max_steps}).")
        
    # Close pages created
    for p in browser_context.pages:
        if p != browser_context.pages[0]:
            try:
                p.close()
            except Exception:
                pass
                
    return {
        "status": status,
        "reason": reason,
        "failure_step": failure_step,
        "total_steps": len(prior_steps)
    }

def main():
    parser = argparse.ArgumentParser(description="Dry run 10 browser workflow tasks.")
    parser.add_argument("--task", type=int, choices=range(1, 11), help="Run a specific task index (1-10) instead of all.")
    parser.add_argument("--start-task", type=int, choices=range(1, 11), default=1, help="Start running from this task index (default: 1).")
    args = parser.parse_args()
    
    os.makedirs("c:/Work/AI_Browser_Assist/screenshots", exist_ok=True)
    
    results = {}
    
    safe_print("Launching Chromium...")
    with sync_playwright() as p:
        browser_context = p.chromium.launch_persistent_context(
            user_data_dir="c:/Work/AI_Browser_Assist/chrome-profile",
            headless=False,
            viewport={"width": 1280, "height": 800}
        )
        
        tasks_to_run = TASKS
        if args.task:
            tasks_to_run = [t for t in TASKS if t["id"] == args.task]
        else:
            tasks_to_run = [t for t in TASKS if t["id"] >= args.start_task]
            
        for task_info in tasks_to_run:
            start_time = time.time()
            res = run_single_task(browser_context, task_info)
            duration = time.time() - start_time
            results[task_info["id"]] = {
                "name": task_info["name"],
                "status": res["status"],
                "reason": res["reason"],
                "failure_step": res["failure_step"],
                "total_steps": res["total_steps"],
                "duration_seconds": round(duration, 1)
            }
            safe_print(f"\nResult: {res['status']} ({res['reason']}) in {duration:.1f}s\n")
            
        browser_context.close()
        
    # Print summary report
    safe_print("\n" + "="*50)
    safe_print("DRY RUN SUMMARY REPORT")
    safe_print("="*50)
    for tid, info in sorted(results.items()):
        safe_print(f"TASK {tid}: {info['name']}")
        safe_print(f"  Status: {info['status']}")
        safe_print(f"  Reason: {info['reason']}")
        safe_print(f"  Steps:  {info['total_steps']}")
        safe_print(f"  Time:   {info['duration_seconds']}s")
        safe_print("-"*50)
        
    # Write summary to file
    with open("c:/Work/AI_Browser_Assist/scratch/dry_run_summary.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    # Force unbuffered output so logs write immediately
    sys.stdout.reconfigure(line_buffering=True)
    main()
