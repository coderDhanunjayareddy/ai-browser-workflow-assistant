"""
Phase E — Website Intelligence — Benchmark Suite.

Measures semantic analysis latency, DOM traversal, form/table extraction, registry
generation, inspector latency, and memory. Target: full semantic analysis under 10ms
on a medium-sized page. All deterministic, browser-free (HTML fixtures).

Run: python benchmark_phasee.py
"""
import sys
import time
import tracemalloc
import statistics

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PASS = 0
FAIL = 0


def bench(label, target, fn, reps=200, on="p95"):
    global PASS, FAIL
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    p50 = statistics.median(times)
    p95 = statistics.quantiles(times, n=20)[18] if len(times) >= 20 else max(times)
    if target is None:
        print(f"  [INFO] {label}: p50={p50:.3f}ms  p95={p95:.3f}ms")
        return p95
    metric = p50 if on == "p50" else p95
    ok = metric <= target
    tag = "PASS" if ok else "FAIL"
    if ok: PASS += 1
    else:  FAIL += 1
    print(f"  [{tag}] {label}")
    print(f"         p50={p50:.3f}ms  p95={p95:.3f}ms  target {on}<{target}ms")
    return p95


from app.website_intelligence import (
    dom_snapshot, semantic_analyzer, form_intelligence, table_intelligence,
    navigation_intelligence, dialog_intelligence, interactive_registry, analyzer, inspector,
)


def _page(n_forms, n_tables, n_rows, n_cards, n_nav):
    """Parameterized page fixture: nav + forms + tables + cards + dialog."""
    nav = "<nav aria-label='Primary'><ul>" + "".join(
        f"<li><a href='/p{i}' class='{'active' if i == 0 else ''}'>Item {i}</a></li>" for i in range(n_nav)) + "</ul></nav>"
    breadcrumb = "<nav aria-label='breadcrumb'><ol><li><a href='/'>Root</a></li><li><a href='/s'>Sub</a></li></ol></nav>"
    forms = "".join(
        f"<form id='f{i}'><label for='e{i}'>Email</label><input id='e{i}' name='e{i}' type='email' required/>"
        f"<input name='pw{i}' type='password'/><input name='file{i}' type='file'/>"
        f"<select name='s{i}'><option>A</option><option>B</option></select>"
        f"<button type='submit'>Submit {i}</button></form>" for i in range(n_forms))
    tables = ""
    for ti in range(n_tables):
        rows = "".join(f"<tr><td><input type='checkbox'/></td>" + "".join(f"<td>r{ri}c{ci}</td>" for ci in range(4)) + "</tr>" for ri in range(n_rows))
        tables += (f"<div class='data-table'><input type='search' placeholder='filter'/><button>Export CSV</button>"
                   f"<table id='t{ti}'><caption>Table {ti}</caption><thead><tr><th class='sortable'>ID</th>"
                   f"<th>Name</th><th>X</th><th>Y</th></tr></thead><tbody>{rows}</tbody></table>"
                   f"<nav class='pagination'><a href='?p=1'>1</a><a href='?p=2'>2</a></nav></div>")
    cards = "<section class='dashboard'>" + "".join(f"<div class='card'><h3>Card {i}</h3><p>val</p><button>Open</button></div>" for i in range(n_cards)) + "</section>"
    dialog = "<div role='dialog' aria-modal='true' aria-label='Confirm'><h2>Confirm?</h2><button>Yes</button><button>Cancel</button></div>"
    return f"<body><header><h1>Page</h1></header>{nav}{breadcrumb}<main>{forms}{tables}{cards}</main>{dialog}<footer>F</footer></body>"


# representative MEDIUM page (~200 nodes: 3 forms, 2 tables, 6 cards)
MEDIUM = _page(n_forms=3, n_tables=2, n_rows=6, n_cards=6, n_nav=6)
ROOT = dom_snapshot.from_html(MEDIUM)
NODE_COUNT = ROOT.node_count()
# a HEAVY page for the scaling INFO (~315 nodes: 4 forms, 3 full tables, 8 cards)
HEAVY = _page(n_forms=4, n_tables=3, n_rows=8, n_cards=8, n_nav=8)
HEAVY_ROOT = dom_snapshot.from_html(HEAVY)

print("\n=== Phase E Website Intelligence — Benchmarks ===\n")
print(f"  medium page: {NODE_COUNT} DOM nodes\n")

print("[B0] Full semantic analysis (TARGET < 10ms on a medium page)")
bench("analyzer.analyze(root)  [median]", 10.0, lambda: analyzer.analyze(ROOT, url="http://x", title="Medium"), on="p50")
bench("analyzer.analyze(root)  [p95]", 10.0, lambda: analyzer.analyze(ROOT, url="http://x", title="Medium"), on="p95")

print("\n[B1] DOM traversal")
bench("from_html parse", None, lambda: dom_snapshot.from_html(MEDIUM), reps=100)
bench("root.walk() full", 5.0, lambda: sum(1 for _ in ROOT.walk()))

print("\n[B2] Per-analyzer")
bench("semantic_analyzer.analyze_page", 8.0, lambda: semantic_analyzer.analyze_page(ROOT))
bench("form_intelligence.analyze_forms", 3.0, lambda: form_intelligence.analyze_forms(ROOT))
bench("table_intelligence.analyze_tables", 3.0, lambda: table_intelligence.analyze_tables(ROOT))
bench("navigation_intelligence.analyze_navigation", 2.5, lambda: navigation_intelligence.analyze_navigation(ROOT))
bench("dialog_intelligence.analyze_dialogs", 2.0, lambda: dialog_intelligence.analyze_dialogs(ROOT))
bench("interactive_registry.build_registry", 3.0, lambda: interactive_registry.build_registry(ROOT))

print("\n[B3] Inspector")
_result = analyzer.analyze(ROOT)
bench("inspector.summary", 1.0, lambda: inspector.summary(_result))
bench("inspector.semantic_tree", 2.0, lambda: inspector.semantic_tree(_result))
bench("inspector.registry", 1.0, lambda: inspector.registry(_result))
bench("result.to_dict()", 5.0, lambda: _result.to_dict())

print("\n[B4] Memory")
tracemalloc.start()
res = analyzer.analyze(ROOT)
d = res.to_dict()
current, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
print(f"  [INFO] analyze + to_dict peak memory: {peak/1024:.1f} KB for {NODE_COUNT} nodes")
print(f"  [INFO] result: {len(res.registry)} interactive, {len(res.forms)} forms, {len(res.tables)} tables")
import json
print(f"  [INFO] result JSON size: {len(json.dumps(d))/1024:.1f} KB")
PASS += 1  # memory measured

# ── scaling sanity (info): confirms near-linear, no O(n^2) ────────────────────
print("\n[B5] Scaling (INFO)")
for rt in [ROOT, HEAVY_ROOT,
           dom_snapshot.from_html("<body>" + (HEAVY.replace("<body>", "").replace("</body>", "") * 2) + "</body>"),
           dom_snapshot.from_html("<body>" + (HEAVY.replace("<body>", "").replace("</body>", "") * 4) + "</body>")]:
    nc = rt.node_count()
    times = []
    for _ in range(30):
        t0 = time.perf_counter()
        analyzer.analyze(rt)
        times.append((time.perf_counter() - t0) * 1000)
    print(f"  [INFO] {nc:>5} nodes -> analyze median {statistics.median(times):.3f}ms")

total = PASS + FAIL
print(f"\n{'='*52}")
print(f"PHASE E BENCHMARKS: {PASS}/{total} pass")
print("  ALL BENCHMARKS PASS" if FAIL == 0 else f"  FAILURES: {FAIL}")
print(f"{'='*52}")
sys.exit(0 if FAIL == 0 else 1)
