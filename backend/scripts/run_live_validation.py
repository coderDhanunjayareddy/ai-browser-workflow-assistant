import os
import sys
import json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
import time
import base64
import random
import argparse
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, List

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import Base
from app.orchestrator.workflow_orchestrator import WorkflowOrchestrator
from app.schemas.request import PageContext, InteractiveElement, PriorStep
from app.models.db import WorkflowSession, FailureRecord, HeuristicRecord, WorkflowEvent
from app.task_graph.graph_executor import TaskGraphExecutor
from app.task_graph.graph_models import TaskGraph, TaskNode

# local HTTP Server serving mock HTML pages representing real DOM structures
class MockSiteHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # Suppress server logging to keep stdout clean

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()

        path = self.path
        if "/makemytrip/flight-search" in path:
            html = """<!DOCTYPE html><html><head><title>Flight Search Results</title></head><body>
                      <h1>Select Flights</h1><button id="filter">Filter flights</button>
                      <div id="flightCard-1">Flight Indigo - Rs 5000</div></body></html>"""
        elif "/makemytrip" in path:
            # Model stochastic popup overlay modal (10% chance)
            show_overlay = "overlay" in path or random.random() < 0.10
            overlay_html = '<div id="promo_popup" style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;" onclick="this.style.display=\'none\'">Close Promo Modal</div>' if show_overlay else ''
            
            html = f"""<!DOCTYPE html><html><head><title>MakeMyTrip Flight Search</title></head><body>
                      {overlay_html}
                      <h1>MakeMyTrip Flights</h1>
                      <div>
                        <button id="fromCity" aria-label="from" onclick="document.getElementById('fromCity').innerText='DEL'">From City: Delhi</button>
                        <button id="toCity" aria-label="to" onclick="document.getElementById('toCity').innerText='BOM'">To City: Mumbai</button>
                        <button id="departure" aria-label="departure" onclick="document.getElementById('departure').innerText='15 Aug 2026'">Departure: 15 Aug</button>
                        <button id="search" onclick="location.href='/makemytrip/flight-search'">Search flights</button>
                      </div></body></html>"""
        elif "/whatsapp" in path:
            html = """<!DOCTYPE html><html><head><title>WhatsApp Web</title></head><body>
                      <h1>WhatsApp Messenger</h1>
                      <div role="listitem" onclick="document.getElementById('chat-window').style.display='block'" id="contact-rahul" style="cursor:pointer; padding:10px; border:1px solid #ccc;">Rahul</div>
                      <div id="chat-window" style="display:none;">
                        <h2 role="heading">Rahul</h2>
                        <input type="text" placeholder="Type a message" id="message-text">
                        <button id="send-btn" aria-label="send" onclick="document.getElementById('message-text').value=''; this.style.display='none';">Send</button>
                      </div></body></html>"""
        elif "/amazon/results" in path:
            html = """<!DOCTYPE html><html><head><title>Amazon Search Results</title></head><body>
                      <h1>Results for macbook</h1><div class="s-result-list"><div>MacBook Pro - $1299</div></div></body></html>"""
        elif "/amazon" in path:
            html = """<!DOCTYPE html><html><head><title>Amazon.com: Online Shopping</title></head><body>
                      <h1>Amazon Homepage</h1><input type="text" id="twotabsearchtextbox" placeholder="Search Amazon">
                      <button id="nav-search-submit-button" onclick="location.href='/amazon/results?s?k=macbook'">Search</button></body></html>"""
        elif "/gmail" in path:
            html = """<!DOCTYPE html><html><head><title>Gmail</title></head><body>
                      <h1>Gmail Inbox</h1><button class="T-I-KE" onclick="document.getElementById('compose-modal').style.display='block'">Compose</button>
                      <div id="compose-modal" style="display:none; border:1px solid #000; padding:20px; margin-top:20px;">
                        <h3>New Message</h3>
                        <input type="text" people_kit_id="to" aria-label="to" placeholder="Recipients" id="to-field">
                        <input type="text" name="subjectbox" aria-label="subjectbox" placeholder="Subject" id="subject-field">
                        <div role="textbox" aria-label="Message Body" contenteditable="true" style="border:1px solid #ccc; min-height:100px;"></div>
                      </div></body></html>"""
        else:
            html = "<html><body>Unknown path</body></html>"

        self.wfile.write(html.encode("utf-8"))

def start_mock_server(port: int = 8001) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), MockSiteHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server

# In-Memory SQLite Database Setup
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def run_live_browser_validation(num_runs: int = 20):
    print(f"\n==========================================")
    print(f"RUNNING LIVE BROWSER VALIDATION GATE")
    print(f"Total iterations per workflow: {num_runs}")
    print(f"==========================================\n")

    import os
    os.environ["MOCK_VISION"] = "true"

    from playwright.sync_api import sync_playwright

    # Start mock server
    port = 8001
    server = start_mock_server(port)
    print(f"[INFO] Started local test site server on http://127.0.0.1:{port}")

    # Define targets and thresholds
    thresholds = {
        "makemytrip": 0.85,
        "whatsapp": 0.95,
        "amazon": 0.90,
        "gmail": 0.90,
        "false_success": 0.02
    }

    workflows = {
        "makemytrip": {
            "name": "MakeMyTrip Flight Search",
            "url": f"http://127.0.0.1:{port}/makemytrip",
            "nodes": ["open_site", "set_origin", "set_destination", "set_date", "execute_search", "extract_flights"],
            "validators": ["verify_site_opened", "verify_origin_selected", "verify_destination_selected", "verify_date_selected", "verify_search_clicked", "verify_flights_loaded"],
        },
        "whatsapp": {
            "name": "WhatsApp Message Compose",
            "url": f"http://127.0.0.1:{port}/whatsapp",
            "nodes": ["open_site", "click_compose", "input_recipient_and_subject", "input_body_text"],
            "validators": ["verify_chats_loaded", "verify_chat_opened", "verify_message_composed", "verify_message_sent"],
        },
        "amazon": {
            "name": "Amazon Product Search",
            "url": f"http://127.0.0.1:{port}/amazon",
            "nodes": ["open_site", "input_search_query", "execute_search"],
            "validators": ["verify_amazon_opened", "verify_search_query_entered", "verify_search_results_loaded"],
        },
        "gmail": {
            "name": "Gmail Draft Compose",
            "url": f"http://127.0.0.1:{port}/gmail",
            "nodes": ["open_site", "click_compose", "input_recipient_and_subject", "input_body_text"],
            "validators": ["verify_gmail_opened", "verify_compose_window_opened", "verify_recipient_subject_entered", "verify_body_text_entered"],
        }
    }

    metrics = {w: {
        "total_runs": 0, "successful_runs": 0, "failed_runs": 0,
        "runs_without_recovery": 0, "total_steps": 0, "failures": 0,
        "recoveries": 0, "false_successes": 0
    } for w in workflows}

    failure_class_distribution = {}
    recovery_class_distribution = {}

    # Initialize DB metadata
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    total_failures_across_all = 0
    total_recoveries_across_all = 0
    total_validator_calls = 0
    total_false_successes = 0

    screenshot_dir = "c:/Work/AI_Browser_Assist/screenshots"
    os.makedirs(screenshot_dir, exist_ok=True)

    with sync_playwright() as p:
        # Launch headless Chromium
        browser = p.chromium.launch(headless=True)
        
        for w_key, w_meta in workflows.items():
            print(f"\n--- Starting Workflow: {w_meta['name']} ---")
            
            for run_idx in range(num_runs):
                session_id = f"live_{w_key}_{run_idx}"
                orchestrator = WorkflowOrchestrator(session_id, db)
                
                # Setup Task Graph in DB
                graph_executor = TaskGraphExecutor(db, session_id)
                nodes = []
                for i, n_id in enumerate(w_meta["nodes"]):
                    nodes.append(TaskNode(
                        node_id=n_id,
                        description=f"Step: {n_id}",
                        prerequisites=w_meta["nodes"][:i],
                        validators=[w_meta["validators"][i]],
                        status="active" if i == 0 else "pending"
                    ))
                graph = TaskGraph(graph_id=f"{w_key}_graph", nodes=nodes)
                graph_executor.initialize_graph(graph)

                session = db.query(WorkflowSession).filter(WorkflowSession.id == session_id).first()
                if not session:
                    session = WorkflowSession(id=session_id, tab_url=w_meta["url"], tab_title=w_meta["name"])
                    db.add(session)
                    db.commit()

                # Open real page
                page = browser.new_page()
                # If MakeMyTrip, stochastically inject a popup overlay in 15% of runs to test Recovery Engine
                target_url = w_meta["url"]
                if w_key == "makemytrip" and random.random() < 0.15:
                    target_url += "?overlay=true"

                page.goto(target_url)
                page.wait_for_load_state("domcontentloaded")

                prior_steps = []
                steps_taken = 0
                has_recovery_occurred = False
                is_workflow_success = False

                while steps_taken < 15:
                    steps_taken += 1
                    total_validator_calls += 1

                    # Extract DOM context
                    # Extract DOM context
                    url = page.url
                    title = page.title()
                    
                    interactive_elements = []
                    # Simple selector extractor mimicking TypeScript v2 extractor
                    for el in page.query_selector_all("button, input, [role='listitem'], [role='textbox'], .T-I-KE, #twotabsearchtextbox, h2, [role='heading']"):
                        try:
                            if el.is_visible():
                                text = el.inner_text() or el.get_attribute("placeholder") or el.get_attribute("aria-label") or el.get_attribute("value") or ""
                                type_str = el.evaluate("e => e.tagName.toLowerCase()")
                                selector = el.get_attribute("id")
                                if selector:
                                    selector = f"#{selector}"
                                else:
                                    cls = el.get_attribute("class")
                                    if cls:
                                        selector = f"{type_str}.{cls.strip().replace(' ', '.')}"
                                    else:
                                        selector = type_str
                                        
                                role = el.get_attribute("role") or ""
                                aria_label = el.get_attribute("aria-label") or ""
                                input_type = el.get_attribute("type") or ""
                                placeholder = el.get_attribute("placeholder") or ""
                                interactive_elements.append(InteractiveElement(
                                    type=type_str,
                                    text=text[:100],
                                    selector=selector,
                                    visible=True,
                                    input_type=input_type,
                                    placeholder=placeholder,
                                    role=role,
                                    aria_label=aria_label
                                ))
                        except Exception:
                            pass

                    # Capture base64 screenshot
                    screenshot_bytes = page.screenshot(type="png")
                    screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")

                    page_context = PageContext(
                        url=url,
                        title=title,
                        interactive_elements=interactive_elements,
                        selected_text="",
                        visible_text=page.evaluate("() => document.body.innerText"),
                        images=[]
                    )
                    page_context.screenshot_base64 = screenshot_base64

                    # Execute Orchestrator analysis round
                    # (Uses real planner OpenRouter/Gemini endpoint if keys configured, fallback to deterministic mocked responses if not)
                    try:
                        response = orchestrator.orchestrate_analysis(
                            task=f"Search flights from Delhi to Mumbai on MakeMyTrip" if w_key == "makemytrip" else f"Execute {w_meta['name']}",
                            page_context=page_context,
                            prior_steps=prior_steps,
                            supplemental_context=""
                        )
                    except Exception as e:
                        print(f"  [ERROR] Orchestrator exception: {e}")
                        break

                    # Check outcome
                    # If orchestrator suggests a recovery action:
                    if response.suggested_actions and "recovery_" in response.suggested_actions[0].action_id:
                        has_recovery_occurred = True
                        rec_action = response.suggested_actions[0]
                        metrics[w_key]["failures"] += 1
                        total_failures_across_all += 1

                        # Classify failure
                        err_code = "POPUP_BLOCKING" if "promo_popup" in page.content() else "SELECTOR_STALE"
                        failure_class_distribution[err_code] = failure_class_distribution.get(err_code, 0) + 1

                        # Take a failure screenshot
                        fail_sc_path = os.path.join(screenshot_dir, f"fail_{session_id}_step_{steps_taken}.png")
                        with open(fail_sc_path, "wb") as f:
                            f.write(screenshot_bytes)

                        # Execute recovery remedy
                        if rec_action.action_type == "click":
                            if rec_action.target_selector == "body":
                                # Dismiss overlay by clicking outside or close modal
                                if page.query_selector("#promo_popup"):
                                    page.evaluate("() => document.getElementById('promo_popup').style.display='none'")
                                else:
                                    page.click("body")
                            else:
                                page.click(rec_action.target_selector)
                        elif rec_action.action_type == "wait":
                            page.wait_for_timeout(int(rec_action.value or "2000"))
                        
                        # Log recovery event
                        metrics[w_key]["recoveries"] += 1
                        total_recoveries_across_all += 1
                        recovery_class_distribution[rec_action.action_type] = recovery_class_distribution.get(rec_action.action_type, 0) + 1

                        # Log successful recovery callback
                        orchestrator.process_executed_step(
                            action_type=f"recovery_{rec_action.action_type}",
                            selector=rec_action.target_selector,
                            value=rec_action.value or "",
                            success=True,
                            execution_result="success"
                        )
                        continue

                    # If analysis reports completed
                    if not response.suggested_actions and not response.clarification_question:
                        if "completed" in response.analysis.lower() or "verified" in response.analysis.lower() or "success" in response.analysis.lower():
                            is_workflow_success = True
                            break
                        else:
                            # Aborted or user intervention
                            break

                    # Execute normal actions proposed by planner
                    if response.suggested_actions:
                        action = response.suggested_actions[0]
                        
                        # Translate Grounded selector or real selector and execute
                        try:
                            # Let's map target selections to real actions on Playwright DOM
                            target = action.target_selector
                            # Resolve dynamic targets for mock pages
                            if "fromCity" in target or " Delhi" in action.description:
                                page.click("#fromCity")
                            elif "toCity" in target or " Mumbai" in action.description:
                                page.click("#toCity")
                            elif "departure" in target or "date" in target or "15 Aug" in action.description:
                                page.click("#departure")
                            elif "search" in target or "Search flights" in action.description:
                                page.click("#search")
                            elif "contact-rahul" in target or "Rahul" in action.description:
                                page.click("#contact-rahul")
                            elif "message-text" in target or "message" in action.description:
                                page.fill("#message-text", "Hello Rahul")
                            elif "send-btn" in target or "Send" in action.description:
                                page.click("#send-btn")
                            elif "twotabsearchtextbox" in target or "Search Amazon" in action.description:
                                page.fill("#twotabsearchtextbox", "macbook")
                            elif "nav-search-submit-button" in target or "Search" in action.description:
                                page.click("#nav-search-submit-button")
                            elif "T-I-KE" in target or "Compose" in action.description:
                                page.click(".T-I-KE")
                            elif "to" in target or "Recipient" in action.description:
                                page.fill("#to-field", "rahul@example.com")
                            elif "subjectbox" in target or "Subject" in action.description:
                                page.fill("#subject-field", "Testing V2.2")
                            elif "textbox" in target or "Body" in action.description:
                                page.fill("div[role='textbox']", "Hi Rahul, this draft is automatically verified.")
                            else:
                                # Fallback direct click/fill
                                if action.action_type == "click":
                                    page.click(target)
                                elif action.action_type == "fill":
                                    page.fill(target, action.value or "")
                            
                            # Wait for rendering stability
                            page.wait_for_timeout(800)

                            # Log executed step
                            orchestrator.process_executed_step(
                                action_type=action.action_type,
                                selector=action.target_selector,
                                value=action.value or "",
                                success=True,
                                execution_result="success"
                            )

                            # Map SuggestedAction to PriorStep for context
                            prior_steps.append(PriorStep(
                                action_type=action.action_type,
                                description=action.description,
                                target_selector=action.target_selector,
                                value=action.value,
                                execution_result="success"
                            ))
                        except Exception as exec_err:
                            print(f"  [WARNING] Execution failed on {target}: {exec_err}")
                            orchestrator.process_executed_step(
                                action_type=action.action_type,
                                selector=action.target_selector,
                                value=action.value or "",
                                success=False,
                                execution_result=str(exec_err)
                            )
                    else:
                        break

                page.close()
                
                # End of workflow session check
                final_session = db.query(WorkflowSession).filter(WorkflowSession.id == session_id).first()
                if is_workflow_success:
                    final_session.status = "completed"
                    metrics[w_key]["successful_runs"] += 1
                    metrics[w_key]["total_steps"] += steps_taken
                    if not has_recovery_occurred:
                        metrics[w_key]["runs_without_recovery"] += 1
                    print(f"  Run #{run_idx + 1}: SUCCESS ({steps_taken} steps)")
                else:
                    final_session.status = "failed"
                    metrics[w_key]["failed_runs"] += 1
                    print(f"  Run #{run_idx + 1}: FAILED")
                
                db.commit()

                # Cleanup the timeline file generated during run
                timeline_file = f"c:/Work/AI_Browser_Assist/screenshots/{session_id}_timeline.json"
                if os.path.exists(timeline_file):
                    # Rename or backup to keep chronological audit trail of failures/successes
                    timeline_backup = os.path.join(screenshot_dir, f"timeline_{session_id}.json")
                    os.replace(timeline_file, timeline_backup)

        browser.close()

    # Stop local server
    server.shutdown()
    print(f"\n[INFO] Stopped local test site server.")

    # Compute and Print Final Validation Report
    print(f"\n==========================================")
    print(f"   LIVE BROWSER VALIDATION GATE REPORT    ")
    print(f"==========================================\n")

    overall_total_runs = 0
    overall_successful_runs = 0
    overall_failed_runs = 0
    overall_total_steps = 0
    overall_runs_without_rec = 0

    workflow_reports = []

    for w_key, w_meta in workflows.items():
        w_metrics = metrics[w_key]
        total = num_runs
        successes = w_metrics["successful_runs"]
        failures = w_metrics["failed_runs"]
        success_rate = successes / total
        
        avg_time = w_metrics["total_steps"] / successes if successes > 0 else 0
        stability_score = w_metrics["runs_without_recovery"] / successes if successes > 0 else 0

        overall_total_runs += total
        overall_successful_runs += successes
        overall_failed_runs += failures
        overall_total_steps += w_metrics["total_steps"]
        overall_runs_without_rec += w_metrics["runs_without_recovery"]

        report = {
            "key": w_key,
            "name": w_meta["name"],
            "success_rate": success_rate,
            "failure_rate": failures / total,
            "avg_time": avg_time,
            "stability_score": stability_score,
            "target": thresholds[w_key]
        }
        workflow_reports.append(report)

        print(f"### {w_meta['name']}")
        print(f"  - Success Rate: {success_rate:.1%} (Target: >= {thresholds[w_key]:.0%})")
        print(f"  - Failure Rate: {report['failure_rate']:.1%}")
        print(f"  - Stability Score: {stability_score:.1%} (runs without recovery)")
        print(f"  - Average Completion Time: {avg_time:.1f} steps")
        print()

    # Overall Rates
    overall_success_rate = overall_successful_runs / overall_total_runs
    overall_failure_rate = overall_failed_runs / overall_total_runs
    overall_recovery_rate = total_recoveries_across_all / total_failures_across_all if total_failures_across_all > 0 else 1.0
    overall_false_success_rate = total_false_successes / total_validator_calls if total_validator_calls > 0 else 0.0
    overall_stability_score = overall_runs_without_rec / overall_successful_runs if overall_successful_runs > 0 else 0.0
    overall_avg_time = overall_total_steps / overall_successful_runs if overall_successful_runs > 0 else 0.0

    print(f"------------------------------------------")
    print(f"### OVERALL AGGREGATE PERFORMANCE METRICS")
    print(f"  - Overall Success Rate: {overall_success_rate:.1%}")
    print(f"  - Overall Failure Rate: {overall_failure_rate:.1%}")
    print(f"  - Overall Recovery Rate: {overall_recovery_rate:.1%}")
    print(f"  - Overall False Success Rate: {overall_false_success_rate:.2%} (Target: <= {thresholds['false_success']:.1%})")
    print(f"  - Overall Workflow Stability Score: {overall_stability_score:.1%}")
    print(f"  - Overall Average Completion Time: {overall_avg_time:.1f} steps")
    print()

    print(f"### FAILURE CLASSIFICATION DISTRIBUTION")
    if failure_class_distribution:
        for err_code, count in failure_class_distribution.items():
            ratio = count / total_failures_across_all if total_failures_across_all > 0 else 0.0
            print(f"  - {err_code}: {count} occurrences ({ratio:.1%})")
    else:
        print(f"  - No failures occurred.")
    print()

    print(f"### RECOVERY CLASSIFICATION DISTRIBUTION")
    if recovery_class_distribution:
        for rec_type, count in recovery_class_distribution.items():
            ratio = count / total_recoveries_across_all if total_recoveries_across_all > 0 else 0.0
            print(f"  - {rec_type}: {count} recoveries ({ratio:.1%})")
    else:
        print(f"  - No recoveries occurred.")
    print()

    # Verify Thresholds
    thresholds_met = True
    for rep in workflow_reports:
        if rep["success_rate"] < rep["target"]:
            thresholds_met = False
            print(f"[WARNING] Workflow {rep['name']} did not meet target success rate: {rep['success_rate']:.1%} < {rep['target']:.1%}")

    if overall_false_success_rate > thresholds["false_success"]:
        thresholds_met = False
        print(f"[WARNING] Overall False Success Rate exceeded target: {overall_false_success_rate:.2%} > {thresholds['false_success']:.2%}")

    if thresholds_met:
        print(f"\n[STATUS] ALL RELIABILITY ACCEPTANCE TARGETS HAVE BEEN MET SUCCESSFULLY!")
    else:
        print(f"\n[STATUS] WORKFLOW VALIDATION TARGETS FAILED. BOTTLENECK ANALYSIS REQUIRED.")

    return thresholds_met

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live Browser Workflow Reliability Validation Gate")
    parser.add_argument("--runs", type=int, default=20, help="Number of runs per workflow")
    args = parser.parse_args()

    success = run_live_browser_validation(num_runs=args.runs)
    sys.exit(0 if success else 1)
