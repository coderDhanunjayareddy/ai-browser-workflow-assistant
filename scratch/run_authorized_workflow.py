"""Diagnostic wrapper: application owns the workflow; operator owns its auth handoff."""
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, str(ROOT / 'backend' / 'scripts'))
import run_live_sidepanel_validation as harness

harness.REPORT_DIR = ROOT / 'scratch' / 'authorized-workflow-evidence'
harness.REPORT_DIR.mkdir(exist_ok=True)
original_text = harness._sidepanel_text
last_print = 0
auth_assisted = False
observing = False
mutations = []

def observe_response(response):
    if response.request.method != 'POST':
        return
    # Record response identities only, never authentication tokens or bodies.
    record = {'url': response.url.split('?')[0], 'status': response.status}
    try:
        data = response.json()
        if isinstance(data, dict):
            record['identity'] = {k: data[k] for k in ('id', 'name', 'title') if k in data}
    except Exception:
        pass
    mutations.append(record)


def panel_text(panel):
    global last_print, auth_assisted, observing
    if not observing:
        observing = True
        panel.context.on('response', observe_response)
    text = original_text(panel)
    if time.time() - last_print > 20:
        print('PROGRESS', text[-1500:].replace(os.environ.get('WORKFLOW_PASSWORD', '\0'), '[redacted]'), flush=True)
        last_print = time.time()
    resume = panel.get_by_role('button', name=re.compile('I completed it.*verify and resume', re.I))
    if not auth_assisted and resume.count() and resume.is_visible():
        origin = os.environ.get('WORKFLOW_AUTH_ORIGIN', '')
        candidates = [p for p in panel.context.pages if f'{urlparse(p.url).scheme}://{urlparse(p.url).netloc}' == origin and p.locator('input[type=password]:visible').count() == 1]
        if len(candidates) == 1:
            target = candidates[0]
            email = target.locator('input[type=email]:visible')
            password = target.locator('input[type=password]:visible')
            submit = target.get_by_role('button', name=re.compile(r'^sign in$', re.I))
            if email.count() == 1 and submit.count() == 1:
                auth_assisted = True
                print('OPERATOR_AUTH_HANDOFF', origin, flush=True)
                email.fill(os.environ['WORKFLOW_EMAIL'])
                password.fill(os.environ['WORKFLOW_PASSWORD'])
                submit.click()
                password.wait_for(state='hidden', timeout=30000)
                resume.click()
                panel.wait_for_timeout(1000)
                text = original_text(panel)
    return text


harness._sidepanel_text = panel_text
try:
    result = harness.main()
finally:
    for path in harness.REPORT_DIR.glob('*.json'):
        path.write_text(path.read_text(encoding='utf-8').replace(os.environ.get('WORKFLOW_PASSWORD', '\0'), '[redacted]'), encoding='utf-8')
    (harness.REPORT_DIR / 'operator-assistance.json').write_text(json.dumps({'authentication_handoff_assisted': auth_assisted}))
    (harness.REPORT_DIR / 'observed-post-responses.json').write_text(json.dumps(mutations, indent=2))
