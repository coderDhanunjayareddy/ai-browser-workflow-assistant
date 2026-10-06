import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services import ai_service

original = ai_service._call_openrouter_chat
directory = ROOT / 'backend' / '.trace_sink' / 'isolated-workflow'
directory.mkdir(parents=True, exist_ok=True)

def call(messages, **kwargs):
    response = original(messages, **kwargs)
    record = json.dumps({'messages': messages, 'response': response}, ensure_ascii=False, indent=2)
    secret = os.environ.get('WORKFLOW_PASSWORD')
    if secret:
        record = record.replace(secret, '[redacted]')
    (directory / f'{time.time_ns()}.json').write_text(record, encoding='utf-8')
    return response

ai_service._call_openrouter_chat = call
import uvicorn
uvicorn.run('app.main:app', host='127.0.0.1', port=8010)
