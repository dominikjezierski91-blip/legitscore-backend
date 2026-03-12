# LegitScore Backend

## Project Overview
LegitScore is an AI system that analyzes football jerseys (soccer shirts) to determine authenticity and classification. Users upload photos, and AI (Gemini Vision) performs forensic-style analysis to generate a risk assessment report in PDF format.

This is **not a simple classification system** — it is a forensic analysis system combining multiple signals (collar construction, sponsor prints, fabric texture, player personalization, stitching, badge materials, tags and labels).

## Tech Stack
- **Backend**: FastAPI (Python 3.13), runs on `uvicorn`
- **Frontend**: Next.js 14 with React 18, Tailwind CSS
- **AI**: Google Gemini Vision API (default model: `gemini-2.5-flash`)
- **PDF Generation**: WeasyPrint

## Project Structure
```
├── app/                    # FastAPI backend
│   ├── main.py            # App entry point, CORS, routes
│   ├── routes/cases.py    # API endpoints for case management
│   ├── services/
│   │   ├── agent_a_gemini.py    # Gemini AI integration
│   │   ├── pdf_report.py        # PDF generation
│   │   └── storage.py           # File/case storage
│   ├── models/            # Pydantic models
│   └── templates/         # Jinja2 templates for reports
├── frontend/              # Next.js frontend
│   ├── app/               # App router pages (important: /case/[case_id])
│   ├── components/        # React components
│   └── lib/               # Utilities and API client
├── data/                  # Runtime data (cases, assets, artifacts)
└── prompt_a.txt           # Agent A system prompt
```

## Running the Project

### Backend
```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm run dev
```

## Environment Variables
- `GEMINI_API_KEY` - Required for AI analysis
- `GEMINI_MODEL` - Model name (default: `models/gemini-2.5-flash`)
- `A_PROMPT_FILE` - Custom prompt file path (default: `prompt_a.txt`)
- `NEXT_PUBLIC_API_BASE_URL` - Backend URL for frontend

## Core Categories

The AI system outputs probabilities for these categories:
- `meczowa` – match issued / player issued jersey
- `oryginalna_sklepowa` – authentic retail jersey
- `oficjalna_replika` – official replica jersey
- `edycja_limitowana` – limited edition
- `treningowa_custom` – training/custom jersey
- `podrobka` – fake / counterfeit

## API Flow

1. `POST /api/cases` - Create new case
2. `POST /api/cases/{id}/assets` - Upload photos
3. `POST /api/cases/{id}/run-decision?mode=basic|expert` - Run AI analysis:
   - Runs Gemini Vision analysis
   - Writes `report_data_raw.json`
   - Normalizes probabilities
   - Writes final `report_data.json`
   - Generates `report.txt` and `report.pdf`
   - Only then sets `case.status = "DECIDED"`
4. `GET /api/cases/{id}/report-data` - Get report data (read-only)
5. `GET /api/cases/{id}/report-pdf` - Download PDF report

## Critical Architecture Rules

### 1. Agent A is the Single Source of Truth
Agent A (Gemini Vision) determines the verdict. Backend must **never override semantic verdict fields**:
- `verdict_category`
- `confidence_percent`
- `confidence_level`
- `summary`
- `label`

Backend may **only normalize** `probabilities` (e.g., 0.6 → 60).

### 2. Snapshot Consistency
All outputs must come from the same snapshot. The result page and PDF must use identical data.

- Never recompute data during GET requests
- GET endpoints must only read files
- Never re-run analysis on read operations

Artifacts stored in: `data/cases/{case_id}/artifacts/`
- `report_data_raw.json` - Raw Agent A output
- `report_data.json` - Final normalized snapshot
- `report.pdf` - Generated PDF

### 3. Single Execution
Analysis must run only once per case. Guard against multiple `run-decision` executions (lock file mechanism).

## Code Style Expectations

Prefer:
- Small isolated fixes
- Minimal changes
- Explicit diffs
- Deterministic behavior

Avoid:
- Rewriting large files
- Introducing hidden logic
- Recomputing values
- Speculative changes

## Debugging Guidelines

When debugging issues:
1. Inspect artifacts: `report_data_raw.json`, `report_data.json`, `report.pdf`
2. Check backend logs
3. Verify snapshot consistency using `report_id` and `analysis_date`

## Key Files
- `app/routes/cases.py` - Main API logic
- `app/services/agent_a_gemini.py` - Gemini integration and response normalization
- `app/templates/report_basic.html` / `report_expert.html` - PDF templates
- `prompt_a.txt` - System prompt defining report schema and analysis criteria

## Language
- Code comments and logs are in Polish
- User-facing content is in Polish
- Communicate with user in Polish unless they switch to English
