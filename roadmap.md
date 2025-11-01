# Shadow Form Automation Roadmap

## Objectives
- Streamline job portal submissions by capturing dynamic forms, letting candidates complete a normalized worksheet, and replaying answers reliably.
- Preserve a local-first experience with auditable artifacts for every capture, worksheet edit, and submission replay.
- Grow portal coverage incrementally while reusing a canonical candidate profile and mapping catalog.

## System Architecture
- **FormCaptureService**: Playwright-driven crawler that walks the target portal, records sections, selectors, labels, field types, option sets, required flags, and reveal actions. Outputs `raw/form_schema.json` and supporting screenshots.
- **WorksheetBuilder**: Generates a "shadow form" UI (lightweight web or TUI) from the captured schema, pre-populates fields from ProfileService defaults, surfaces validation hints, and writes user edits to `derived/worksheet_answers.json` plus database tables for reuse.
- **ProfileService**: Maintains canonical candidate data (contact info, experience snippets, long-form answers) and reusable transformers for formatting (dates, paragraph lengths). Serves defaults to WorksheetBuilder and ReplayExecutor.
- **ReplayExecutor**: Applies worksheet answers back into the live portal via Playwright, handles stage sequencing, triggers DOM events, uploads documents, and generates submission artifacts (`submission/replay_log.json`, confirmation metadata, proof screenshots).
- **Telemetry & Mapping Catalog**: Logs unknown selectors, validation failures, and portal fingerprints to expand the selector/label to canonical-field mapping store, informing future auto-population.

## Data Flow
1. Existing intake captures job metadata and artifact directory.
2. FormCaptureService run stores schema snapshots and screenshots under the job artifacts.
3. WorksheetBuilder session loads schema, merges profile defaults, and persists candidate-confirmed answers plus notes.
4. ReplayExecutor consumes schema + answers, performs submission, and records results for audit and status tracking.

## Phase Plan
- **Phase 0 – Baseline**: Document schema contracts, add instrumentation hooks to the current manual prefill runner, and establish fixtures/tests.
- **Phase 1 – Capture**: Implement FormCaptureService for an initial portal family (e.g., Greenhouse), persist schemas, and validate coverage via automated tests with recorded pages.
- **Phase 2 – Worksheet**: Deliver a minimal worksheet interface (FastAPI-rendered web page or CLI TUI) that renders captured forms, applies profile defaults, enforces required fields, and stores edits.
- **Phase 3 – Replay**: Build ReplayExecutor to drive Playwright submissions using worksheet answers, manage uploads, and emit telemetry plus submission artifacts.
- **Phase 4 – Portal Expansion**: Extend selector catalogs, add portal classifiers, and support user-approved mappings for new field labels.
- **Phase 5 – Automation Polish**: Layer in AI assist for long-form answers, tighter CLI workflows, and integration with compliance/tailoring pipelines.

## Data & Schema Needs
- Database additions for candidate profile fields, worksheet answer revisions, portal schema metadata, and replay logs.
- Artifact taxonomy updates for `raw/form_schema.json`, `derived/worksheet_answers.json`, and `submission/replay_log.json`.
- Versioned schema definitions to keep backward compatibility as portal-specific attributes evolve.

## Open Questions
- Preferred worksheet UX (offline-friendly CLI vs. lightweight web) and how to sync state across devices.
- Policy for auto-populating sensitive answers versus requiring explicit user confirmation per run.
- Storage strategy for uploads (resume variants, cover letters) alongside worksheet state for quick replay and manual review.

## Immediate Next Steps
1. Finalize JSON schema specs for form capture and worksheet answers; add repo documentation and sample fixtures.
2. Prototype FormCaptureService against a single portal to validate selector extraction, stage tracking, and artifact outputs.
3. Define profile data contracts so defaults can prefill the worksheet with minimal user input.
