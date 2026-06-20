# AI Browser Workflow Assistant

A Chrome Extension (MV3) that reads the active webpage, sends context to a FastAPI backend,
receives AI-suggested actions, presents them for your approval, and executes only what you approve.

## Prerequisites

- Node.js 20+
- Python 3.11+
- Docker Desktop (for PostgreSQL)
- Chrome 114+ (required for Side Panel API)

---

## 1. Start PostgreSQL

```bash
docker compose up -d
```

Postgres will be available at `localhost:5432`.

---

## 2. Run the Backend

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Copy environment config
copy .env.example .env        # Windows
# cp .env.example .env        # macOS/Linux

# Choose an AI provider and add the matching key in backend/.env.
# For the currently working OpenRouter path:
# AI_PROVIDER=openrouter
# OPENROUTER_API_KEY=...
# OPENROUTER_MODEL=openai/gpt-4o-mini

# Optional: verify the configured key and model before using the extension
python check_openrouter.py

# Start the server
python run.py
```

Backend runs at: http://localhost:8000

Verify: open http://localhost:8000/health in your browser.
Expected: `{"status":"ok","db":"connected"}`

API docs: http://localhost:8000/docs

If you use Gemini instead, set `AI_PROVIDER=gemini`, configure
`GEMINI_API_KEY` and `GEMINI_MODEL`, then run `python check_gemini.py`.
If `/analyze` returns provider access or quota errors, run the matching checker
from the `backend` folder before using the extension.

---

## 3. Build the Extension

```bash
cd extension

# Install dependencies
npm install

# Development build with watch mode
npm run dev

# Production build
npm run build
```

Output is written to `extension/dist/`.

---

## 4. Load the Extension in Chrome

1. Open Chrome and go to `chrome://extensions`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked**
4. Select the `extension/dist/` folder
5. The AI Browser Assistant icon appears in the toolbar

Click the toolbar icon — the side panel opens on the right side of the browser.

---

## Project Structure

```
ai-browser-assist/
├── extension/          Chrome Extension (MV3) — React + TypeScript
├── backend/            FastAPI backend — Python
├── docs/               Architecture, roadmap, decisions, API spec, workflows
└── docker-compose.yml  PostgreSQL for local development
```

## Documentation

- [Architecture](docs/architecture.md)
- [Roadmap](docs/roadmap.md)
- [Engineering Decisions](docs/decisions.md)
- [API Specification](docs/api-spec.md)
- [Workflows](docs/workflows.md)
