# Run the First M0 Baseline — Operator Runbook

**Audience:** a developer running the M0 real-website benchmark for the first time.
**Goal:** produce the first **real** baseline reports (JSON + Markdown + HTML) so the M0.5
architecture analysis can be done on measured data instead of estimates.
**Do this on your own machine** (real Chrome session, real network, real AI provider).

Everything below has been verified against the current code. Where a published doc is
stale, this runbook overrides it (noted inline).

---

## 0. TL;DR (the whole sequence)

```bash
# from repo root
docker compose up -d                              # PostgreSQL (host port 5433)

cd backend
python -m venv .venv
.venv\Scripts\activate                            # Windows  (mac/linux: source .venv/bin/activate)
pip install -r requirements.txt                   # backend deps
pip install -r requirements-benchmark.txt         # benchmark deps (playwright, requests, pyyaml)
playwright install chromium                        # one-time browser download (~150 MB)

# confirm AI provider key works (uses whatever AI_PROVIDER is set to in backend/.env)
python check_openrouter.py                         # or: python check_gemini.py

python run.py                                       # starts backend on http://localhost:8000
```

Then, in a **second terminal** (keep the backend running):

```bash
cd backend
.venv\Scripts\activate

# 1) prove the harness itself is healthy (3 offline fixtures through the real loop)
python -m benchmark.m0_runner --self-test

# 2) full baseline, trusted-driver mode
python -m benchmark.m0_runner --suite nightly --executor playwright \
    --backend http://localhost:8000 \
    --output benchmark/reports/m0-baseline-playwright.json --headless

# 3) full baseline, production-fidelity mode (synthetic events)
python -m benchmark.m0_runner --suite nightly --executor synthetic \
    --backend http://localhost:8000 \
    --output benchmark/reports/m0-baseline-synthetic.json --headless

# 4) lock the playwright run as the official baseline (cheap: just copy the report you
#    already generated — same format as a baseline file). Windows / mac-linux:
copy benchmark\reports\m0-baseline-playwright.json benchmark\baselines\nightly.json
# cp   benchmark/reports/m0-baseline-playwright.json benchmark/baselines/nightly.json
```

When done, send me **both** `benchmark/reports/m0-baseline-playwright.json` and
`benchmark/reports/m0-baseline-synthetic.json` (and the `.html` if you want a visual).

---

## 1. Prerequisites

| Requirement | Why | Check |
|---|---|---|
| Python 3.11+ | backend + benchmark | `python --version` |
| Docker Desktop | PostgreSQL for the backend | `docker --version` |
| Chrome/Chromium auto-installed by Playwright | the benchmark drives a real browser | step 3 below |
| Network egress | real-site tasks hit youtube/github/amazon/etc. | `curl -I https://www.youtube.com` |
| A working AI provider key in `backend/.env` | the loop calls the live `/analyze` → real model | step 4 below |

> You do **not** need Node.js or the Chrome extension to run the benchmark. The benchmark
> injects the extension's content-script logic directly; it does not load the extension.

---

## 2. Start PostgreSQL (required)

The backend's `/analyze` path **writes to PostgreSQL** (session + verified-facts state). A
file SQLite fallback is **not recommended** — the sync endpoints run in FastAPI's threadpool
and the app creates the engine without `check_same_thread=False`, so file SQLite will raise
cross-thread errors. Use Postgres.

```bash
# from repo root (where docker-compose.yml lives)
# the compose file needs a POSTGRES_PASSWORD; it must equal the one in the DB URL (postgres)
#   Windows PowerShell:   $env:POSTGRES_PASSWORD="postgres"
#   mac/linux:            export POSTGRES_PASSWORD=postgres
docker compose up -d
docker compose ps           # postgres should be "healthy"
```

**Port note (important):** `docker-compose.yml` maps host **5433** → container 5432
(`"5433:5432"`), and the backend default `DATABASE_URL` is
`postgresql://postgres:postgres@localhost:5433/ai_browser_assist`. The repo `README.md`
says "localhost:5432" — that is **stale; the correct host port is 5433**. Leave the default
`DATABASE_URL` as-is and it will match the compose mapping.

---

## 3. Install the backend + benchmark, and the browser

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate                       # Windows   (mac/linux: source .venv/bin/activate)

pip install -r requirements.txt              # FastAPI, SQLAlchemy, provider SDK, ...
pip install -r requirements-benchmark.txt    # playwright>=1.45, requests, PyYAML
playwright install chromium                  # downloads the Chromium build Playwright drives
```

`requirements-benchmark.txt` is intentionally separate from `requirements.txt` — the
benchmark is a dev/CI tool, never a production dependency.

---

## 4. Configure + verify the AI provider

The benchmark calls the live backend, which uses whatever provider `backend/.env` selects.

**Currently configured in this repo's `backend/.env`:** `AI_PROVIDER=openrouter`,
`OPENROUTER_MODEL=openai/gpt-4o-mini` (both an OpenRouter key and a Gemini key are present).
So by default the baseline will reason with **OpenRouter gpt-4o-mini**.

Required env vars (in `backend/.env`, loaded automatically regardless of cwd):

| Variable | Needed when | Default |
|---|---|---|
| `AI_PROVIDER` | always | `gemini` (repo .env sets `openrouter`) |
| `OPENROUTER_API_KEY` + `OPENROUTER_MODEL` | `AI_PROVIDER=openrouter` | model `openai/gpt-4o-mini` |
| `GEMINI_API_KEY` + `GEMINI_MODEL` | `AI_PROVIDER=gemini` | model `gemini-2.5-flash` |
| `DATABASE_URL` | optional override | `postgresql://postgres:postgres@localhost:5433/ai_browser_assist` |

Verify the key/model BEFORE running (saves a wasted run):

```bash
python check_openrouter.py        # if AI_PROVIDER=openrouter
# python check_gemini.py          # if AI_PROVIDER=gemini
```

A clean response means the provider path works. A 401/403/429 here will also fail every
benchmark step — fix it first.

---

## 5. Start the backend

```bash
cd backend
.venv\Scripts\activate
python run.py            # equivalent to: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Confirm health in a browser or curl:

```bash
curl http://localhost:8000/health
# expected: {"status":"ok","db":"connected"}
```

If `db` is `disconnected`, Postgres is not reachable — see §2 and §12.

Leave this terminal running. Do everything below in a **second** terminal.

---

## 6. Step 1 — harness self-test (do this first, every time)

```bash
cd backend
.venv\Scripts\activate
python -m benchmark.m0_runner --self-test
```

This runs the **3 fixture tasks in the smoke suite** (login, pagination, modal) through the
real browser + real `/analyze`. It asserts **≥90% completion (i.e. all 3) and zero
INFRASTRUCTURE errors**, then prints `SELF-TEST PASS` (exit 0) or `FAIL` (exit 2).

> The self-test is a fast smoke gate over 3 fixtures, **not** all 11. For fuller offline
> coverage (all 11 local fixtures, still real `/analyze`, no real-site network), run:
> ```bash
> python -m benchmark.m0_runner --suite nightly --site fixture_server --executor playwright \
>     --backend http://localhost:8000 --output benchmark/reports/m0-fixtures.json --headless
> ```
> Expect close to 11/11; drag-drop/file patterns are the likeliest fixture misses.

- **PASS** → the loop, executor, capture, criteria, and backend wiring all work; real-site
  numbers will be meaningful. Proceed.
- **FAIL** → do **not** trust any real-site data. The problem is the harness/backend, not the
  websites. See §12.

---

## 7. Step 2 — the baseline runs

Run the full suite in **both** executor modes. The gap between them is the headline M0.5
finding (it quantifies the execution-fidelity problem M1 targets).

```bash
# Mode A — trusted Playwright input (upper bound on reasoning/grounding)
python -m benchmark.m0_runner --suite nightly --executor playwright \
    --backend http://localhost:8000 \
    --output benchmark/reports/m0-baseline-playwright.json --headless

# Mode B — verbatim extension synthetic events (today's production reality)
python -m benchmark.m0_runner --suite nightly --executor synthetic \
    --backend http://localhost:8000 \
    --output benchmark/reports/m0-baseline-synthetic.json --headless
```

Notes:
- Drop `--headless` to **watch** the browser (also reduces anti-bot blocking on some sites).
- `--site <site_id>` runs one site; `--task <task_id>` runs one task — useful for retries.
- Auth-gated tasks (Gmail, Google Docs/Sheets, LinkedIn, Canva) will print `SKIP ...` because
  no recorded login exists. That is expected for the first baseline (see §8).
- Each run prints a live line per task and a final `DONE completion=… cost=…` summary.

### Lock the official baseline

After you're satisfied (ideally after 2–3 low-variance runs), write the locked baseline that
CI and future milestones compare against:

```bash
python -m benchmark.m0_runner --suite nightly --executor playwright --headless --update-baseline
# writes benchmark/baselines/nightly.json
```

---

## 8. Authentication & browser state (optional for the first baseline)

The first baseline does **not** require any logins — auth-gated tasks simply SKIP.

If you later want to cover them, record a session once (headed), saved to
`benchmark/.playwright_state/{site}.json` (gitignored — store in the team vault, refresh
~every 14 days):

```bash
python -m benchmark.record_auth --site google_com --url https://accounts.google.com
python -m benchmark.record_auth --site linkedin_com --url https://www.linkedin.com/login
python -m benchmark.record_auth --site canva_com --url https://www.canva.com/login
```

`google_com.json` covers Gmail, Docs, and Sheets. Once present, those tasks stop skipping.

---

## 9. Expected runtime

Wall-clock is dominated by model latency + per-step network-idle waits (~6–10 s/step),
not by the harness (framework overhead is <1 ms/op).

| Run | Tasks executed | Rough time |
|---|---|---|
| `--self-test` (3 smoke fixtures) | 3 | 1–3 min |
| `--suite nightly --site fixture_server` (all 11 fixtures) | 11 | 5–10 min |
| `--suite smoke` | 5 | 2–4 min |
| `--suite nightly`, one mode (no auth recorded) | 22 (11 fixtures + 11 no-auth; 5 auth SKIP) | 20–40 min |
| `--suite nightly`, **both** modes | 44 | 40–75 min |

Real-site tasks that get blocked (CAPTCHA/anti-bot) finish fast, which often shortens the
real total.

---

## 10. Expected API cost

Per `/analyze` step ≈ ~1–3k prompt tokens (compressed to ≤30 elements + system prompt) +
~150–400 completion tokens. A full nightly run is on the order of ~100–150 model calls.

- **OpenRouter `gpt-4o-mini`** (current default): roughly **$0.10–$0.50 per full run**, so
  **under ~$1 for both modes**.
- **Gemini `gemini-2.5-flash`**: similar order of magnitude.

> **Known limitation — the report's cost/token fields will read `0`.** The live
> `/analyze` response does not return a `usage` block, so the benchmark cannot capture token
> counts; `estimated_cost_usd` and `total_tokens` in the reports will be **0.00 / 0**. This
> is a measurement gap, not a free run. **Read your real spend from the provider dashboard**
> (OpenRouter / Google AI Studio) for the run window. (Wiring provider usage into the
> response is a small future task — out of M0 scope, do not do it now.)

---

## 11. Expected artifacts

After a run you will have (paths relative to `backend/`):

| Artifact | Path | Committed? |
|---|---|---|
| JSON report (canonical) | `benchmark/reports/m0-baseline-*.json` | gitignored |
| Markdown report | `benchmark/reports/m0-baseline-*.md` | gitignored |
| HTML report (self-contained) | `benchmark/reports/m0-baseline-*.html` | gitignored |
| Locked baseline (only with `--update-baseline` or copy) | `benchmark/baselines/nightly.json` | **committed** |
| Per-step screenshots | `benchmark/screenshots/<run_id>/<task_id>/step_*.png` | gitignored |
| Per-step DOM snapshots | `benchmark/dom_snapshots/<run_id>/<task_id>/step_*.json` | gitignored |

> **The only valid baseline** is a report produced by `m0_runner` and stored at
> `benchmark/baselines/nightly.json`. The synthetic demos in `benchmark/examples/`
> (`example-report.{json,md,html}`) are tagged `_EXAMPLE`; `m0_runner` and `ci_check`
> refuse them, and baseline resolution never searches `reports/` or `examples/`.

**Send me the two `*.json` reports** (playwright + synthetic). The HTML is the nicest to read
(open it directly in a browser — it is fully self-contained, no server needed).

---

## 12. Common failure modes & recovery

| Symptom | Cause | Recovery |
|---|---|---|
| `/health` shows `"db":"disconnected"` | Postgres not up / wrong port / password mismatch | `docker compose ps`; ensure `POSTGRES_PASSWORD=postgres` before `docker compose up -d`; confirm `DATABASE_URL` uses port **5433** |
| `playwright._impl…Executable doesn't exist` | forgot the browser download | `playwright install chromium` |
| `ModuleNotFoundError: benchmark` (or `app`) | not running from `backend/` | `cd backend` and ensure the venv is active |
| Self-test FAIL, fixtures not completing | backend down, provider key bad, or loop regression | check `/health`; run `check_openrouter.py`/`check_gemini.py`; re-run `--self-test --task fixture__login_form` to isolate |
| Every `/analyze` returns 401/403 | provider key invalid / no model access | fix `backend/.env`; re-run the checker script |
| `/analyze` returns 429 a lot | provider rate limit | wait; rerun the affected `--task`; consider a paid tier |
| All real-site tasks BLOCKED (captcha/anti-bot) | headless detection on Amazon/Flipkart/etc. | expected — BLOCKED ≠ FAILED (excluded from completion rate); retry with `--headless` removed |
| Auth tasks all SKIPPED | no recorded login state | expected for first baseline; see §8 to add later |
| Report `estimated_cost_usd` = 0 | `/analyze` returns no usage block | expected (see §10); read real cost from provider dashboard |
| Run interrupted partway | crash / Ctrl-C | reports are written only at the end; just re-run the suite command (idempotent; new `run_id`) |
| A single task hangs | site stall | each task is bounded by its `timeout_ms`/`max_steps`; it will self-terminate as TIMEOUT and the run continues |

To isolate problems fast: `--site fixture_server` (offline only), then `--site youtube_com`,
then widen. Use `--task <task_id>` to rerun exactly one task.

---

## 13. After the run

1. Confirm the self-test PASSED and that fixture tasks COMPLETED in the real run (if fixtures
   fail on real sites' run too, the data is suspect — re-investigate before sharing).
2. Send me `m0-baseline-playwright.json` and `m0-baseline-synthetic.json`.
3. We then perform the **M0.5 architecture analysis** on the real numbers: failure breakdown,
   execution-gap analysis, evidence-based M1 scope, ROI, roadmap adjustment, and stop-list.

Until those real reports exist, no M0.5 analysis will be produced — the whole point of M0 is
to decide M1 from measured evidence, not estimates.
