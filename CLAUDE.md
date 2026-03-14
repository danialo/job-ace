# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Job Ace is a local-first job application automation system built with FastAPI (backend), SQLAlchemy (database), Playwright (browser automation), and vanilla JavaScript (frontend). All data is stored locally in SQLite with filesystem artifacts organized by job ID.

## Common Commands

### Environment Setup
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .

# Install development dependencies
pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium

# Initialize database
job-ace init
```

### Development Server
```bash
# Start the web server (preferred)
./start.sh

# Or manually
python -m backend.main

# Server runs at http://localhost:3000
# API docs: http://localhost:3000/docs
# ReDoc: http://localhost:3000/redoc
```

### Testing and Linting
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov

# Lint code
ruff check .
```

### CLI Commands
```bash
# Convert resume to XML
job-ace convert-resume <resume-file> [--output-file <output.xml>]

# Load resume blocks from YAML or XML
job-ace load-blocks example_resume_blocks.yaml

# Capture job posting
job-ace intake <job-url>
job-ace intake <job-url> --force  # Re-capture even if exists

# Tailor resume
job-ace tailor <job-id> <comma-separated-block-ids>
# Example: job-ace tailor 1 1,2,3,4

# Capture application form (browser automation)
job-ace capture <job-id>
job-ace capture <job-id> --no-headless  # Run browser visibly

# Generate prefill plan
job-ace prefill-plan <job-id>

# Execute prefill automation
job-ace apply <worksheet-path>

# Log submission
job-ace log-submit <job-id> [--confirmation-id ID] [--confirmation-text "text"] [--screenshot-path path]
```

## Architecture

### High-Level Flow
```
User (Web UI or CLI)
    ↓
FastAPI Backend (backend/api/app.py)
    ↓
Services Layer (backend/services/)
    ├── IntakeService → Fetch & parse job postings (httpx + Playwright fallback)
    ├── TailorService → Generate tailored resumes from blocks
    ├── CaptureService → Extract form schemas via browser automation
    ├── PrefillPlanner → Build automation plans for form filling
    └── SubmissionLogger → Track application submissions
    ↓
Data Layer
    ├── SQLite Database (db.sqlite3)
    └── Artifacts (artifacts/job-<id>/)
```

### Database Schema (backend/models/models.py)

Key relationships:
- **Company** 1→N **JobPosting** (one company has many job postings)
- **JobPosting** 1→1 **Application** (each job gets one application record)
- **JobPosting** 1→N **Artifact** (job postings have multiple file artifacts)
- **Application** N→N **ResumeBlock** (via ResumeBlockUsage junction table)

Status flow for JobPosting:
- `intake` → job captured and parsed
- Can transition to other states during tailoring/application process

Status flow for Application:
- `draft` → not yet submitted
- `submitted` → application sent
- Other custom statuses as needed

### Artifact Management (backend/services/artifacts.py)

Artifacts are organized by job ID with content-based deduplication (SHA256):

```
artifacts/
└── job-<id>/
    ├── raw/              # Original captures
    │   ├── posting.html
    │   ├── posting.txt
    │   └── posting.pdf
    ├── derived/          # Generated content
    │   ├── jd.json
    │   ├── tailor_request.json
    │   ├── tailor_response.json
    │   ├── resume_body_v1.md
    │   └── resume_ats_v1.txt
    └── submission/       # Application records
        ├── worksheet_answers.json
        ├── replay_log.json
        └── screenshot.png
```

The `ArtifactManager` class handles:
- Directory creation per job
- Writing text/binary files with automatic SHA256 deduplication
- Tracking artifacts in the database with kind, path, and hash

### LLM Integration (backend/services/llm.py)

Supports both **OpenAI** (production) and **StubLLMClient** (development/testing) with **dual-model strategy** for optimal quality and cost:

#### Dual-Model Strategy

**Why different models for different tasks?**
- **Job Extraction**: Fast, structured data extraction → GPT-4o-mini (cheap, structured outputs)
- **Resume Tailoring**: Critical precision for job applications → o1-mini/o3/GPT-5 (reasoning models)

Resume tailoring affects real job outcomes, so we use reasoning models that:
- Provide deeper analysis with chain-of-thought reasoning
- Better understand nuanced matches between experience and requirements
- Minimize hallucinations and errors that could hurt applications

#### OpenAI Client (`OpenAIClient`)

**Extraction** (`extract_job_json`):
- Uses GPT-4o-mini by default (fast, structured outputs via Pydantic schemas)
- Extracts: title, company, location, salary, employment type, seniority
- Categorizes: must-haves vs nice-to-haves, screening questions
- Can upgrade to GPT-4o or GPT-5 for better accuracy

**Tailoring** (`tailor_resume`):
- Uses o1-mini by default (reasoning model for precision)
- Performs detailed requirement-by-requirement analysis
- Rates evidence strength (strong/moderate/weak/missing)
- Identifies gaps and suggests specific improvements
- Provides ATS keyword optimization
- Can upgrade to o3-mini, o3, or GPT-5 for maximum reliability

#### Stub Client (`StubLLMClient`)
- **Development fallback**: Deterministic regex-based extraction
- **No API costs**: Good for testing and development
- **Limited accuracy**: Simple pattern matching, no semantic understanding

#### Configuration

The `get_llm_client(settings, task)` factory selects the appropriate model:
- `task="extraction"` → Uses `llm_extraction_model` setting
- `task="tailoring"` → Uses `llm_tailoring_model` setting
- Falls back to StubLLMClient if no API key or model == "stub-model"

Environment variables:
- `OPENAI_API_KEY`: OpenAI API key (also checks `JOB_ACE_OPENAI_API_KEY`)
- `JOB_ACE_LLM_EXTRACTION_MODEL`: Model for job extraction (default: `gpt-4o-mini`)
- `JOB_ACE_LLM_TAILORING_MODEL`: Model for resume tailoring (default: `o1-mini`)

**Recommended models by budget:**
- **Budget**: extraction=gpt-4o-mini, tailoring=o1-mini
- **Quality**: extraction=gpt-4o, tailoring=o3-mini
- **Best**: extraction=gpt-4o or gpt-5, tailoring=o3 or gpt-5

### Browser Automation (backend/browser/)

Uses Playwright for:
- **Fallback fetching** (intake.py): When httpx fails, Playwright renders JS-heavy pages
- **Form capture** (capture.py): Screenshots and DOM analysis of application forms
- **Form filling** (prefill.py): Automated application submission based on plans

Important configuration (`backend/config.py`):
- `playwright_headless`: Toggle browser visibility
- `intake_user_agent`: Mimics real browser to avoid bot detection

### Resume Block System

Resume blocks are reusable, tagged sections stored in the `resume_block` table:
- **category**: Type of content (summary, experience, education, skills)
- **tags**: Comma-separated tags for filtering (python, backend, leadership)
- **text**: The actual content
- **version**: Track iterations of blocks

Load from YAML:
```yaml
- category: summary
  tags: [software-engineer, full-stack]
  text: |
    Professional summary here...
```

Or from XML (uses namespace `http://job-ace.local/resume`):
```xml
<resume xmlns="http://job-ace.local/resume">
  <blocks>
    <block>
      <category>summary</category>
      <tags><tag>python</tag></tags>
      <content>Professional summary...</content>
    </block>
  </blocks>
</resume>
```

## Configuration

Settings via environment variables (prefix `JOB_ACE_`) or `.env` file:
- `JOB_ACE_DATA_ROOT`: Artifact storage directory (default: `artifacts/`)
- `JOB_ACE_DATABASE_URL`: Database connection (default: `sqlite:///./db.sqlite3`)
- `JOB_ACE_PLAYWRIGHT_HEADLESS`: Browser headless mode (default: `true`). Set to `false` for debugging or Cloudflare challenges.
- `JOB_ACE_INTAKE_USER_AGENT`: User-Agent string for job fetching (default: Chrome 121 on Windows). Update to latest Chrome UA if sites start blocking.
- **LLM Configuration** (dual-model strategy):
  - `OPENAI_API_KEY` or `JOB_ACE_OPENAI_API_KEY`: OpenAI API key
  - `JOB_ACE_LLM_EXTRACTION_MODEL`: Model for job parsing (default: `gpt-4o-mini`)
  - `JOB_ACE_LLM_TAILORING_MODEL`: Model for resume tailoring (default: `o1-mini`)
  - Use `stub-model` for either to disable OpenAI and use regex fallback

## Important Implementation Details

### Session Management
Always use context manager for database sessions:
```python
from backend.db.session import get_session

with get_session() as session:
    # Your database operations
    service = IntakeService(session)
    result = service.run(url)
```

### Intake Fallback Strategy (Bot Detection Solution)

**Critical Context**: Major job boards (Indeed, LinkedIn, etc.) use Cloudflare and aggressive bot detection that returns 403 Forbidden for automated requests. This was the primary blocker that required moving development between machines.

**Solution Implemented** (`backend/services/intake.py:84-132`):

`IntakeService._fetch_html()` uses a two-tier fetch strategy:

1. **First attempt: httpx** with realistic browser headers
   - Fast for simple pages
   - Includes User-Agent, Accept, Accept-Language, Referer from Google
   - If status < 400: return immediately
   - If status ≥ 400 or HTTPError: fall back to Playwright

2. **Fallback: Playwright with anti-detection measures**
   - Launches real Chromium browser (headed or headless via `JOB_ACE_PLAYWRIGHT_HEADLESS`)
   - `--disable-blink-features=AutomationControlled` (hides automation flags)
   - Sets realistic viewport (1280×880), locale (en-US)
   - Applies same headers as httpx attempt
   - Waits for `domcontentloaded` then `networkidle` (20s timeout)
   - Properly closes browser context even on errors

**Anti-Detection Measures**:
- User agent configurable via `JOB_ACE_INTAKE_USER_AGENT` (defaults to Chrome 121 on Windows)
- Referer header set to `https://www.google.com/` (simulates organic traffic)
- Disables Chromium automation flags that Cloudflare detects
- Viewport and locale configuration to match real users

**When to Use Headed Mode**:
Set `JOB_ACE_PLAYWRIGHT_HEADLESS=false` in `.env` for:
- Debugging Cloudflare challenges
- Sites that detect headless browsers
- Manual CAPTCHA solving (future feature)

**Logging**:
- `"Fetching job posting"` with `method: "httpx"` → initial attempt
- `"HTTP fetch failed, falling back to browser"` → httpx failed, using Playwright
- `"Fetched job posting via Playwright"` with `source: "playwright"` → success

This architecture allows fast fetching for simple pages while surviving bot detection on protected sites.

### Resume Converter (backend/services/resume_converter.py)
Supports PDF, DOCX, and TXT input:
- PDF: Uses pypdf for text extraction
- DOCX: Uses python-docx for paragraph extraction
- TXT: Direct text processing
- Output: Structured XML with namespace `http://job-ace.local/resume`

### File Exclusions (.gitignore)
User resume files (*.pdf, *.docx, *.xml) are excluded except:
- `example_resume_blocks.xml`
- Schema files in `docs/schemas/*.xsd`

Test files matching `test_resume*` or `danial_resume*` patterns are excluded.

## Troubleshooting

### Intake Returns 403 or Cloudflare Challenge
1. Check logs for `"HTTP fetch failed, falling back to browser"` - should auto-fallback to Playwright
2. If Playwright also fails, try headed mode: `JOB_ACE_PLAYWRIGHT_HEADLESS=false job-ace intake <url>`
3. Watch browser window for CAPTCHA or challenges
4. Update User-Agent to latest Chrome version in `.env` if detection improves
5. Some sites may require additional stealth measures (canvas fingerprinting, etc.)

### Playwright Browser Not Found
```bash
playwright install chromium
# Or reinstall all browsers
python -m playwright install
```

### pydantic-settings Import Error
The config module requires pydantic-settings (added for bot detection work):
```bash
pip install -e .  # Reinstall package to get new dependencies
```

## Development Notes

### Adding New Service Methods
1. Create service class in `backend/services/`
2. Accept `db: Session` in `__init__`
3. Use `ArtifactManager` for file operations
4. Add CLI command in `cli/app.py` using `@app.command()` decorator
5. Add API endpoint in `backend/api/app.py` if needed

### Testing Patterns
See existing tests in `tests/`:
- `test_analysis_service.py`: Service layer testing
- `test_schemas.py`: Pydantic model validation
- `test_prefill_planner.py`: Business logic testing
- `test_llm_stub.py`: Stub client verification

Use pytest with async support:
```python
import pytest
from backend.db.session import get_session

@pytest.fixture
def db_session():
    with get_session() as session:
        yield session
```

### Frontend Structure
Vanilla JavaScript with 4-tab interface:
- Tab 1 (Capture Job): Intake job postings
- Tab 2 (Tailor Resume): Generate tailored resumes
- Tab 3 (Capture Form): Browser automation setup
- Tab 4 (Apply): Log submissions

Frontend communicates with FastAPI via fetch() calls to documented endpoints.

## Roadmap Context

Current status: Week 1 MVP (working features)
- Job capture with Cloudflare bypass, resume tailoring, form capture, prefill planning, submission logging
- OpenAI integration for intelligent job parsing and resume analysis

Future enhancements:
- Multi-step form workflows
- Portal-specific selector catalogs
- Scoring and ranking engine
- Enhanced compliance checking
- NEVER hardcode IP addresses in this project. This is a local-first application — always use `localhost` or `127.0.0.1`. No external IPs should appear anywhere in the codebase, configs, or documentation.