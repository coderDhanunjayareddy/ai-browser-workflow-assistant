"""
Phase D — Adaptive Execution & Recovery — Benchmark Suite.

Phase D is additive: it must add negligible overhead to the existing adapter while
improving reliability. Targets (in-process, deterministic):
  B1. classify_failure        < 0.5ms
  B2. recovery.recover()      < 1ms
  B3. adaptive resolve        < 0.5ms
  B4. execution validation    < 1ms
  B5. monitor start+finish    < 0.5ms
  B6. metrics record+get      < 1ms
  B7. adapter Phase D click   < 2ms   (full adaptive path, fake page)
  Phase C click overhead is reported as INFO for comparison; real-browser
  recovery latency is reported as INFO. No gateway overhead change.

Run: python benchmark_phased.py
"""
import sys
import time
import statistics

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PASS = 0
FAIL = 0


def bench(label, target, fn, reps=300):
    global PASS, FAIL
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    p50 = statistics.median(times)
    p95 = statistics.quantiles(times, n=20)[18] if len(times) >= 20 else max(times)
    if target is None:
        print(f"  [INFO] {label}: p50={p50:.4f}ms  p95={p95:.4f}ms")
        return p95
    ok = p95 <= target
    tag = "PASS" if ok else "FAIL"
    if ok: PASS += 1
    else:  FAIL += 1
    print(f"  [{tag}] {label}")
    print(f"         p50={p50:.4f}ms  p95={p95:.4f}ms  target<{target}ms")
    return p95


from app.execution_gateway.browser import failure_classes as fc
from app.execution_gateway.browser import recovery as rec
from app.execution_gateway.browser import adaptive_resolver as ar
from app.execution_gateway.browser import execution_validation as ev
from app.execution_gateway.browser import monitor as mon
from app.execution_gateway.browser import metrics as met
from app.execution_gateway.browser.playwright_adapter import PlaywrightAdapter
from app.execution_gateway.models import make_command, CommandType, RetryConfig


class FakeLocator:
    def __init__(self, page): self.page = page
    def click(self, **k): pass
    def fill(self, t, **k): pass
    def count(self): return 1
    def input_value(self): return "v"
    def scroll_into_view_if_needed(self, **k): pass
class FakePage:
    def __init__(self): self.url = "https://x/p"; self.body = "ok"
    def is_closed(self): return False
    def goto(self, u, **k): self.url = u
    def title(self): return "T"
    def locator(self, s): return FakeLocator(self)
    def get_by_test_id(self, v): return FakeLocator(self)
    def get_by_label(self, v): return FakeLocator(self)
    def get_by_placeholder(self, v): return FakeLocator(self)
    def get_by_text(self, v): return FakeLocator(self)
    def inner_text(self, sel): return self.body
    def wait_for_timeout(self, ms): pass
    def wait_for_load_state(self, s, timeout=None): pass
class FakeSession:
    def __init__(self): self.page = FakePage(); self.active_tab_id = "tab-0"; self.downloads = []; self.context = None
    def ensure_page(self): return self.page
    def screenshot(self, l=""): return None
    def refresh(self): pass
class FakeMgr:
    def __init__(self): self.s = FakeSession()
    def get_or_create(self, e, headless=True): return self.s
    def get(self, e): return self.s
    def close(self, e): return True
class _Cmd:
    def __init__(self, p): self.parameters = p

_analysis = fc.classify_failure(Exception("element is hidden"), phase="click")
_session = FakeSession()
_cmd_v = type("C", (), {"parameters": {"validate_after": {"url_contains": "x"}}})()

print("\n=== Phase D Adaptive Execution & Recovery — Benchmarks ===\n")

print("[B1] Failure classification")
bench("classify_failure()", 0.5, lambda: fc.classify_failure(Exception("element is hidden"), phase="click"))

print("\n[B2] Recovery engine")
bench("recovery.recover()", 1.0, lambda: rec.recover(_analysis, FakeSession(), _Cmd({"testid": "x"})))

print("\n[B3] Adaptive resolution")
bench("adaptive resolve (testid)", 0.5, lambda: ar.resolve(FakePage(), {"testid": "go"}))
bench("adaptive resolve (extended walk)", 0.5, lambda: ar.resolve(FakePage(), {"placeholder": "Search"}))

print("\n[B4] Execution validation")
bench("execution_validation.validate()", 1.0,
      lambda: ev.validate("click", FakeSession(), _cmd_v, pre_state={"url": "https://x/p"}))

print("\n[B5] Monitor")
def _mon_cycle():
    r = mon.start_step("eb", "s", 1, "click", 0.0)
    mon.finish_step(r, finished_at=0.001, attempts=1, outcome="completed", locator_strategy="testid")
bench("monitor start+finish", 0.5, _mon_cycle)
mon._reset_for_testing()

print("\n[B6] Metrics")
def _met_cycle():
    met.record_step(succeeded=True, retries=0, elapsed_ms=1.0, locator_strategy="testid")
    met.get_metrics()
bench("metrics record+get", 1.0, _met_cycle)
met._reset_for_testing()

print("\n[B7] Adapter overhead (fake page)")
pd = PlaywrightAdapter(execution_id="bd", session_manager=FakeMgr(),
                       adaptive=True, recovery=True, post_validation=True)
pc = PlaywrightAdapter(execution_id="bc", session_manager=FakeMgr())   # Phase C (flags off)
def _click(a): a.click(make_command(CommandType.click, "s", 1, "b", parameters={"testid": "go"}))
bench("adapter Phase D click", 2.0, lambda: _click(pd))
bench("adapter Phase C click (INFO, comparison)", None, lambda: _click(pc))
mon._reset_for_testing(); met._reset_for_testing()

# ── Real browser recovery latency (INFO; guarded) ─────────────────────────────
def _chromium_ok():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True); b.close()
        return True
    except Exception as e:
        print(f"\n  (chromium unavailable — real-browser benchmark skipped: {str(e)[:50]})")
        return False

if _chromium_ok():
    import socket, threading, http.server, socketserver
    HTML = b"<!doctype html><html><head><title>B</title></head><body><h1 id='h'>Hi</h1><button id='go' data-testid='go'>Go</button></body></html>"
    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(HTML))); self.end_headers(); self.wfile.write(HTML)
        def log_message(self, *a): pass
    _s = socket.socket(); _s.bind(("127.0.0.1", 0)); port = _s.getsockname()[1]; _s.close()
    httpd = socketserver.TCPServer(("127.0.0.1", port), _H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    URL = f"http://127.0.0.1:{port}/"
    from app.execution_gateway.browser import session as bs
    bs._reset_for_testing()
    real = PlaywrightAdapter(execution_id="bench-real-d", headless=True,
                             adaptive=True, recovery=True, post_validation=True)
    real.navigate(make_command(CommandType.navigate, "w", 0, URL, parameters={"url": URL}))
    print("\n[B8] Real browser (Phase D path) — INFO")
    bench("navigate (real, Phase D)", None,
          lambda: real.navigate(make_command(CommandType.navigate, "s", 1, URL, parameters={"url": URL})), reps=15)
    bench("click (real, Phase D, no recovery needed)", None,
          lambda: real.click(make_command(CommandType.click, "s", 1, "go", parameters={"testid": "go"})), reps=15)
    real.close(); httpd.shutdown(); bs._reset_for_testing()

total = PASS + FAIL
print(f"\n{'='*52}")
print(f"PHASE D BENCHMARKS: {PASS}/{total} pass")
print("  ALL BENCHMARKS PASS" if FAIL == 0 else f"  FAILURES: {FAIL}")
print(f"{'='*52}")
sys.exit(0 if FAIL == 0 else 1)
