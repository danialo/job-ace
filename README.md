# Job Ace

**Local-First Job Application Assistant**

Job Ace is an intelligent job application automation system that helps you capture job postings, tailor your resume, and streamline the application process.

## Features

- **Job Posting Capture**: Automatically fetch and parse job postings from URLs
- **Resume Tailoring**: Match your resume blocks to job requirements and generate tailored resumes
- **Form Capture**: Capture application form schemas using Playwright automation
- **Prefill Planning**: Generate automated form-filling plans
- **Application Tracking**: Log and track your job applications
- **Modern Web UI**: Clean, intuitive interface for managing your job search
- **Local-First**: All data stored locally in SQLite with filesystem artifacts

## Quick Start

### 1. Installation

```bash
# Clone the repository (if not already done)
cd job-ace

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .

# Install Playwright browsers
playwright install chromium
```

### 2. Initialize Database

```bash
job-ace init
```

### 3. Load Resume Blocks

Create a YAML file with your resume blocks (see `example_resume_blocks.yaml`):

```yaml
- category: summary
  tags: [software-engineer, full-stack]
  text: |
    Your professional summary here...

- category: experience
  tags: [python, backend]
  text: |
    Your work experience here...
```

Load the blocks:

```bash
job-ace load-blocks example_resume_blocks.yaml
```

### 4. Start the Web Interface

```bash
./start.sh
```

Or manually:

```bash
python -m backend.main
```

The web interface will be available at: **http://172.239.66.45:3000**

## Using the Web Interface

### Tab 1: Capture Job

1. Enter a job posting URL
2. Click "Capture Job" to fetch and analyze the posting
3. The system extracts job title, company, requirements, and other metadata
4. Job details are saved to the database with all artifacts

### Tab 2: Tailor Resume

1. Select a captured job from the dropdown
2. Enter comma-separated resume block IDs (e.g., `1,2,3,4`)
3. Optionally specify a resume version
4. Click "Generate Tailored Resume" to create a customized resume
5. View the tailored resume with coverage metrics

### Tab 3: Capture Form

1. Select a job to capture its application form
2. Use the CLI for browser automation: `job-ace capture <job_id>`
3. Generate a prefill plan from the captured form schema

### Tab 4: Apply

1. Select a job you've applied to
2. Enter confirmation details (ID, message, screenshot path)
3. Click "Log Submission" to record the application
4. Track your application status

## CLI Commands

### Initialize Database
```bash
job-ace init
```

### Convert Resume to XML
```bash
job-ace convert-resume <resume-file> [--output-file <output.xml>]

# Examples:
job-ace convert-resume my_resume.pdf --output-file my_resume.xml
job-ace convert-resume my_resume.docx  # Prints to stdout
job-ace convert-resume my_resume.txt --output-file resume.xml
```

### Load Resume Blocks
```bash
job-ace load-blocks <yaml-or-xml-file>
```

### Capture Job Posting
```bash
job-ace intake <job-url>
job-ace intake <job-url> --force  # Re-capture even if exists
```

### Tailor Resume
```bash
job-ace tailor <job-id> <block-ids>
# Example: job-ace tailor 1 1,2,3,4
```

### Capture Application Form
```bash
job-ace capture <job-id>
```

### Generate Prefill Plan
```bash
job-ace prefill-plan <job-id>
```

### Apply (Execute Prefill)
```bash
job-ace apply <worksheet-path>
```

### Log Submission
```bash
job-ace log-submit <job-id>
```

## API Documentation

Once the server is running, visit:
- **Swagger UI**: http://172.239.66.45:3000/docs
- **ReDoc**: http://172.239.66.45:3000/redoc

### Available Endpoints

- `POST /intake` - Capture job posting
- `POST /tailor` - Generate tailored resume
- `POST /prefill-plan` - Generate form prefill plan
- `POST /log-submit` - Log application submission
- `GET /artifact/{job_id}` - Retrieve artifact path

## Project Structure

```
job-ace/
├── backend/              # FastAPI backend
│   ├── api/             # API endpoints
│   ├── browser/         # Playwright automation
│   ├── db/              # Database session management
│   ├── models/          # SQLAlchemy models & schemas
│   ├── services/        # Business logic
│   └── utils/           # Utilities
├── cli/                 # Typer CLI
├── frontend/            # Web UI
│   ├── static/
│   │   ├── css/        # Styles
│   │   └── js/         # JavaScript
│   └── index.html      # Main page
├── tests/               # Test suite
├── docs/                # Documentation
├── artifacts/           # Local storage for job data
├── db.sqlite3          # SQLite database
└── pyproject.toml      # Project configuration
```

## Data Storage

### Database (SQLite)
- **job_posting**: Job details and metadata
- **company**: Company information
- **application**: Application status and tracking
- **resume_block**: Reusable resume sections
- **artifact**: File artifacts with deduplication

### Filesystem Artifacts
Organized by job ID in `artifacts/`:
```
artifacts/
└── job-<id>/
    ├── raw/              # Original captures
    │   ├── posting.html
    │   ├── posting.text
    │   └── jd.json
    ├── derived/          # Generated content
    │   ├── tailor_request.json
    │   ├── tailor_response.json
    │   └── resume_<version>.txt
    └── submission/       # Application records
        ├── worksheet_answers.json
        └── replay_log.json
```

## Architecture

```
User (Web UI or CLI)
    ↓
FastAPI Backend
    ↓
Services Layer
    ├── IntakeService → Capture job postings
    ├── TailorService → Generate tailored resumes
    ├── CaptureService → Extract form schemas
    ├── PrefillPlanner → Build automation plans
    └── SubmissionLogger → Track applications
    ↓
Database (SQLite) + Artifacts (Filesystem)
```

## Technologies

- **Backend**: FastAPI, SQLAlchemy, Pydantic
- **CLI**: Typer
- **Automation**: Playwright
- **Database**: SQLite with aiosqlite
- **Frontend**: Vanilla JavaScript, HTML5, CSS3
- **Parsing**: BeautifulSoup4, YAML
- **Utilities**: structlog, httpx, Jinja2

## Development

### Running Tests
```bash
pytest
pytest --cov  # With coverage
```

### Linting
```bash
ruff check .
```

### Install Development Dependencies
```bash
pip install -e ".[dev]"
```

## Roadmap

See `roadmap.md` for the full project vision and planned features.

### Current Status (Week 1 MVP)
- ✅ Job posting capture and parsing
- ✅ Resume tailoring system
- ✅ Form schema capture
- ✅ Prefill planning
- ✅ Application logging
- ✅ Web UI interface
- ✅ CLI commands

### Coming Soon
- Real LLM integration (Claude, GPT)
- Advanced form parsing (multi-step workflows)
- Portal-specific selector catalogs
- Enhanced compliance checking
- Scoring and ranking engine
- Worksheet UI for form filling
- Multi-device sync

## Contributing

This is a week-one MVP. Contributions, bug reports, and feature requests are welcome!

## License

MIT

## Notes

- This system is designed for **authorized use only** - use it responsibly and ethically
- Always respect website terms of service and robots.txt
- The system stores data locally for privacy and control
- Playwright automation requires proper browser drivers (installed via `playwright install`)

## Support

For issues or questions, check the documentation in `docs/` or review the code.

## Example Workflow

1. **Start the server**: `./start.sh`
2. **Open the web UI**: http://172.239.66.45:3000
3. **Capture a job**: Enter URL in "Capture Job" tab
4. **Load resume blocks**: `job-ace load-blocks example_resume_blocks.yaml`
5. **Tailor resume**: Select job and blocks in "Tailor Resume" tab
6. **Generate prefill plan**: Use "Capture Form" tab
7. **Apply**: Fill out application and log it in "Apply" tab
8. **Track**: Monitor your applications

Happy job hunting! 🎯
