# Job Ace

**Local-First Job Application Assistant**

Job Ace is an intelligent job application automation system that helps you capture job postings, parse and tailor your resume, and streamline the application process. All data stays on your machine.

## Features

- **Resume Intake**: Upload PDF/DOCX/TXT resumes with multi-stage LLM parsing into structured blocks
- **Structured Experience Metadata**: Job title, company, and dates anchored to each experience block
- **Job Posting Capture**: Fetch and parse job postings with Cloudflare bypass (httpx + Playwright fallback)
- **Resume Tailoring**: Match resume blocks to job requirements with coverage analysis
- **Form Capture**: Capture application form schemas using Playwright automation
- **Prefill Planning**: Generate automated form-filling plans
- **Application Tracking**: Log and track your job applications
- **Multi-Provider LLM**: OpenAI (GPT-4.1, GPT-4o-mini), Anthropic (Claude), or offline stub
- **Modern Web UI**: 5-tab interface with Quill.js rich text editing
- **Local-First**: All data stored locally in SQLite with filesystem artifacts

## Quick Start

### 1. Installation

```bash
cd job-ace

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# Install dev dependencies (for testing)
pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium
```

### 2. Start the Web Interface

```bash
./start.sh
```

Or manually:

```bash
python -m backend.main
```

The web interface will be available at: **http://localhost:3000**

### 3. Configure LLM Provider

By default, Job Ace uses a stub LLM client with regex-based heuristics. For production use, configure OpenAI or Anthropic:

```bash
# Create .env file
cat > .env << 'EOF'
# OpenAI (recommended)
OPENAI_API_KEY=sk-your-key-here

# Or Anthropic
# JOB_ACE_LLM_PROVIDER=anthropic
# JOB_ACE_ANTHROPIC_API_KEY=sk-ant-your-key-here
EOF
```

**Dual-model strategy** — different models for different tasks:

| Task | Default Model | Config Variable |
|---|---|---|
| Job extraction | `gpt-4o-mini` | `JOB_ACE_LLM_EXTRACTION_MODEL` |
| Resume parsing | `gpt-4.1` | `JOB_ACE_LLM_RESUME_PARSING_MODEL` |
| Resume tailoring | `gpt-4.1` | `JOB_ACE_LLM_TAILORING_MODEL` |

Set any model to `stub-model` to disable LLM for that task and use regex fallback.

## Using the Web Interface

### Tab 1: Resume Intake

1. Upload your resume (PDF, DOCX, or TXT)
2. The system parses it into structured blocks using multi-stage LLM analysis
3. Preview and edit individual blocks with the Quill rich text editor
4. Experience blocks show structured metadata (job title, company, dates)
5. Compare original resume side-by-side with parsed blocks

### Tab 2: Capture Job

1. Enter a job posting URL
2. Click "Capture Job" to fetch and analyze the posting
3. The system extracts title, company, requirements, and metadata
4. Handles Cloudflare-protected sites via Playwright fallback

### Tab 3: Tailor Resume

1. Select a captured job from the dropdown
2. Choose which resume blocks to include
3. Click "Generate Tailored Resume" with coverage analysis
4. View keyword coverage, uncovered requirements, and compliance check

### Tab 4: Capture Form

1. Select a job to capture its application form schema
2. Generate a prefill plan for automated form filling

### Tab 5: Apply

1. Select a job you've applied to
2. Enter confirmation details and optional screenshot
3. Track application status

## CLI Commands

```bash
job-ace init                          # Initialize database
job-ace convert-resume <file>         # Convert resume to XML
job-ace load-blocks <file.yaml>       # Load resume blocks from YAML/XML
job-ace intake <url> [--force]        # Capture job posting
job-ace tailor <job-id> <block-ids>   # Tailor resume (e.g. job-ace tailor 1 1,2,3)
job-ace capture <job-id>              # Capture application form
job-ace prefill-plan <job-id>         # Generate prefill plan
job-ace apply <worksheet-path>        # Execute prefill automation
job-ace log-submit <job-id>           # Log application submission
```

## API Documentation

Once the server is running, visit:
- **Swagger UI**: http://localhost:3000/docs
- **ReDoc**: http://localhost:3000/redoc

### Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/intake` | Capture job posting |
| `POST` | `/tailor` | Generate tailored resume |
| `POST` | `/parse-resume` | Parse resume (preview) |
| `POST` | `/confirm-resume-blocks` | Save parsed blocks |
| `POST` | `/upload-resume` | Upload and auto-save resume |
| `POST` | `/prefill-plan` | Generate form prefill plan |
| `POST` | `/log-submit` | Log application submission |
| `POST` | `/blocks/{id}/improve` | Improve block via LLM |
| `GET` | `/jobs` | List all jobs |
| `GET` | `/blocks` | List all resume blocks |
| `GET` | `/applications` | List all applications |
| `GET` | `/artifact/{job_id}` | Retrieve artifact path |
| `PUT` | `/blocks/{id}` | Update a resume block |
| `DELETE` | `/blocks/{id}` | Delete a resume block |
| `DELETE` | `/blocks` | Delete all blocks |

## Architecture

```
User (Web UI or CLI)
    |
FastAPI Backend (localhost:3000)
    |
Services Layer
    ├── IntakeService     → Capture job postings (httpx + Playwright)
    ├── TailorService     → Generate tailored resumes
    ├── ResumeConverter   → Multi-stage resume parsing
    ├── AnalysisService   → Job page analysis
    ├── PrefillPlanner    → Build automation plans
    └── SubmissionLogger  → Track applications
    |
LLM Layer (OpenAI / Anthropic / Stub)
    |
Data Layer
    ├── SQLite Database (db.sqlite3)
    └── Artifacts (artifacts/<job-dir>/)
```

## Testing

```bash
# Run backend tests (84 tests)
pytest

# Run with coverage
pytest --cov

# Run E2E Playwright tests (17 tests)
pytest tests/e2e/ -m e2e

# Run everything
pytest -m "" tests/
```

**101 tests total** covering services, API endpoints, models, schemas, LLM factory, and E2E browser tests.

## Project Structure

```
job-ace/
├── backend/
│   ├── api/             # FastAPI endpoints
│   ├── browser/         # Playwright automation
│   ├── db/              # Database session management
│   ├── models/          # SQLAlchemy models & Pydantic schemas
│   └── services/        # Business logic (intake, tailor, LLM, etc.)
├── cli/                 # Typer CLI
├── frontend/
│   ├── static/
│   │   ├── css/         # Styles
│   │   └── js/          # Vanilla JavaScript
│   └── index.html       # Main page (5-tab interface)
├── tests/
│   ├── e2e/             # Playwright browser tests
│   ├── conftest.py      # Shared fixtures (isolated in-memory DB)
│   └── test_*.py        # Unit and integration tests
├── artifacts/           # Local storage for job data
├── db.sqlite3           # SQLite database
└── pyproject.toml       # Project configuration
```

## Technologies

- **Backend**: FastAPI, SQLAlchemy, Pydantic
- **LLM**: OpenAI (GPT-4.1, GPT-4o-mini), Anthropic (Claude), structured outputs
- **CLI**: Typer
- **Automation**: Playwright
- **Database**: SQLite
- **Frontend**: Vanilla JavaScript, Quill.js, HTML5, CSS3
- **Testing**: pytest, pytest-playwright, FastAPI TestClient

## License

MIT
