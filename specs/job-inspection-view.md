# Job Inspection View

## Problem

After capturing a job, the user sees title/company/location but has no visibility into what was actually extracted — requirements, skills, salary, screening questions. That data exists in `jd.json` but is buried in the filesystem.

The capture step is not complete when parsing finishes. It is complete when the user can answer:

- Did we extract the right company/title?
- Did we pull the real must-haves?
- Did we miss deal-breakers?
- Is this job worth tailoring against?

The UI needs to support **verification**, not just storage.

## UI Pattern

Inline expansion on the Capture Job tab:

- **Collapsed card = summary** (current Recent Jobs view)
- **Expanded card = inspection surface**
- One open at a time (clicking another collapses the first)

This is a first-class review step, not a convenience feature.

## Expanded Card Sections

### A. Decision-Critical (always visible when expanded)

- Title
- Company
- Location
- Remote / hybrid / onsite
- Employment type
- Seniority
- Salary range
- Visa / clearance / travel requirements
- Apply deadline
- Original posting link

These are the fields most likely to determine "do I care?"

### B. Match-Critical

- Must-haves
- Nice-to-haves
- Responsibilities
- Screening questions
- Tools / tech stack
- Years-of-experience requirements
- Education / cert requirements

Do **not** bury responsibilities. They are often the missing bridge between keywords and actual fit.

### C. Debug / Provenance (collapsed by default)

- Portal hint
- Capture timestamp
- Apply URL
- Artifact directory path
- Parser / extractor version
- Confidence / extraction quality flags
- "Show raw text" toggle
- "Show raw JSON" toggle

## Capture Quality Banner

At the top of the expanded job, show a small status summary:

- Parsed sections found: N/M
- Must-haves: N
- Nice-to-haves: N
- Screening questions: N
- Salary: found / missing
- Raw text length: N chars

This helps the user instantly see whether extraction was thin or rich, and helps debug parser quality without reading the whole payload.

## Empty-State Semantics

Differentiate between:

- **Not found in posting** — the job didn't include this info
- **Not extracted** — extraction failed or was incomplete
- **Not supported by current parser** — parser doesn't handle this field yet
- **Present in raw text, extraction uncertain** — low confidence

Even a lightweight version helps:
- "No salary found"
- "No screening questions detected"
- "Responsibilities not extracted for this source"

## API

### Keep list endpoint lightweight

`GET /jobs` — returns summary fields only (id, title, company, location, captured_at, portal, salary summary, extraction_status)

### Add detail endpoint

`GET /jobs/{job_id}` — returns normalized response:

```json
{
  "job": {
    "id": 123,
    "title": "Senior Systems Engineer",
    "company": "Acme",
    "location": "Remote"
  },
  "extracted": {
    "must_haves": [],
    "nice_to_haves": [],
    "responsibilities": [],
    "screening_questions": [],
    "tech_stack": [],
    "salary": null,
    "employment_type": null,
    "seniority": null
  },
  "provenance": {
    "source_url": "...",
    "apply_url": "...",
    "portal": "greenhouse",
    "captured_at": "...",
    "artifact_dir": "...",
    "extractor": "anthropic",
    "extractor_version": "x.y.z"
  },
  "raw": {
    "text_available": true,
    "text_preview": "..."
  }
}
```

**Key**: Normalize the parser output into a stable DTO before it hits the frontend. Do not let the frontend depend directly on whatever shape `jd.json` currently has.

### Optional future endpoint

`GET /jobs/{job_id}/artifacts` — returns artifact presence (jd.json exists, raw.txt exists, form_schema.json exists, tailored resumes count)

## Data Architecture

### Read-only, not editable

If extraction is wrong, re-capture with force refresh. Do not allow hand-editing of extracted data without also handling:

- Auditability
- Provenance
- Divergence from source
- Stale tailored outputs derived from edited data

Future: **user annotations** as a separate layer, not mutation of extracted JD.

- `extracted_data` = machine-derived
- `user_annotations` = human corrections / notes

Do not blur those yet.

## Reusability

Build the job detail component as a reusable **JobRequirementsPanel** rather than hardcoded to Capture Job tab. Later reuse on the Tailor tab as a side panel showing requirements while selecting blocks.

## Small Actions on Expanded View

- **Copy requirements** (must-haves + nice-to-haves to clipboard)
- **Copy artifact path** / **Open artifact folder**
- **Re-capture with force refresh**

## Extraction Confidence / Warnings

Even a crude version helps:

- "Salary extracted from ambiguous text"
- "Location inferred from header"
- "Must-haves section unusually short"
- "Posting appears truncated"
- "Apply URL differs from source URL"

## v1 Scope

### UI
- Expandable Recent Jobs cards
- One open at a time
- Decision-critical summary at top
- Must-haves / nice-to-haves / responsibilities / screening questions
- Capture quality banner
- Collapsed metadata/debug section
- Collapsed raw text section
- Re-capture button

### API
- `GET /jobs/{job_id}` with normalized response shape

### Backend
- Loader reads `jd.json`
- Converts to stable DTO
- Includes section presence / counts

## Open Questions

- [ ] Define exact DTO boundary (normalized response schema)
- [ ] Extraction confidence scoring — heuristic vs LLM-based?
- [ ] How to handle partially extracted fields (e.g., salary found but ambiguous)?
- [ ] Should quality banner counts come from DB or re-computed from artifacts?
