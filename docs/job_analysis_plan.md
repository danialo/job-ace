# Job Page Analysis Rollout Plan

## Context

The week-one MVP already captures postings via simple HTTP fetch + BeautifulSoup, stores resume blocks, and offers a manual-prefill Playwright helper. To deliver the envisioned "click a job, get a fit rating, and optionally autofill" flow we need structured page capture, an analysis pipeline, and downstream scoring + form filling that share artifacts.

## End-to-End Workflow (Target State)

1. **Trigger (CLI/UI)**
   - User selects a job URL from an inbox/watch list or pastes it into the CLI.
   - System runs `intake` (existing) *plus* an enhanced analysis pipeline when a fresh capture is desired.

2. **Browser Capture Layer**
   - Use Playwright (headless by default, headful when debugging) to load the page, execute minimal interactions (dismiss modals, expand descriptions), and serialize:
     - Raw HTML after dynamic content settles.
     - Visible text blocks with DOM metadata (section titles, bullet lists, labels, etc.).
     - Optional structured data (schema.org JSON-LD) when present.
     - Screenshots for artifacts.
   - Persist the capture bundle under the job's artifact directory (`raw/browser_capture.*`).

3. **Parsing & Normalization**
   - Run fast BeautifulSoup/heuristic parsing on the captured HTML/text bundle to extract a normalized job description object:
     - Title, company, location (fallback to existing StubLLM heuristics).
     - `requirements`: list of bullet strings grouped by "must have" vs "nice to have" detectors.
     - `responsibilities`, `company_info`, `compensation`, `application_instructions` sections.
   - Persist as JSON (`derived/jd_structured.json`) and keep a digest in DB for traceability.

4. **Resume Block Inventory**
   - Load candidate resume blocks from DB (existing) and optionally allow tagging/weighting.
   - Prepare searchable representations (token sets, embeddings later) once per job run.

5. **Fit Scoring Engine**
   - Deterministic heuristics first:
     - Token overlap score between requirements and blocks.
     - Category-aware boosts (e.g., matching `skills` tags).
     - Flag uncovered critical requirements.
   - Output metrics (0–100 overall score, per-section scores, uncovered gaps) and pointers to supporting blocks.
   - Persist results to artifacts (`derived/fit_report.json`) and update DB columns for quick retrieval.
   - Maintain compliance checks (existing) as a follow-up stage using the tailored resume snapshot.

6. **Form Prefill Planner**
   - Reuse captured job metadata to improve field planning:
     - Map company, title, candidate info into selectors (extensible mapping file per portal).
     - Provide scoring context (e.g., highlight missing info before submission).
   - Continue to hand the plan to `run_prefill` for execution; extend plan schema as needed.

7. **User Feedback Loop**
   - CLI/API surfaces:
     - Summary (score, uncovered requirements, recommended blocks) on demand.
     - Commands to export tailored resume/cover letter, open artifact folder, or launch prefill flow.
   - Allow the user to mark outcomes (applied, declined) which updates application status.

## Key Components To Build

- `backend/browser/analyzer.py`: Playwright capture orchestrator returning structured snapshot.
- `backend/services/analysis.py`: Service layer to orchestrate capture, parsing, and persistence; coordinates with Intake artifacts.
- `backend/services/scoring.py`: Deterministic fit scoring heuristics against resume blocks.
- Schema additions:
  - DB columns for `analysis_json_path`, `fit_score`, `fit_breakdown_json` on `JobPosting` (or `Application`).
  - Artifact kind labels for the new files.
- API/CLI endpoints:
  - `POST /analyze` (job_id or URL) to trigger capture + scoring.
  - CLI command `job-ace analyze <job-url|job-id>` to run pipeline and print summary.

## Incremental Delivery Plan

1. **Phase 1 – Infrastructure**
   - Add browser analyzer + analysis service skeletons with stubbed extraction to unblock downstream work.
   - Create new artifact kinds + DB fields; wire migrations (if/when Alembic comes online).

2. **Phase 2 – Parsing & Scoring**
   - Implement heuristic parsers for requirements/responsibilities sections.
   - Build scoring heuristics leveraging resume blocks + tags.
   - Write unit tests with fixture HTML/resume blocks to validate scoring edge cases.

3. **Phase 3 – API/CLI Integration**
   - Expose `analyze` endpoint/command; ensure idempotency & caching of captures.
   - Tie into existing tailoring/compliance flows (optionally auto-run tailoring post-analysis).

4. **Phase 4 – Prefill Enhancements**
   - Enrich prefill planner with parsed metadata and scoring context.
   - Expand Playwright automation for portal-specific selectors.

## Open Questions / Future Enhancements

- Which resume version should scoring consider by default (latest tailored vs. base blocks)?
- Should analysis run automatically during `intake`, or remain an explicit follow-up command to manage Playwright cost?
- How do we surface human-in-the-loop adjustments (e.g., confirm/unconfirm detected requirements)?
- Long-term: swap StubLLMClient for real model, add embeddings for semantic match, capture compliance heuristics per jurisdiction.

