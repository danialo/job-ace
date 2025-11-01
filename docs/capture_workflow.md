# Capture Workflow

This describes the Phase 1 capture process that generates a normalized shadow-form schema and artifacts.

- CLI: `job-ace capture <job_id> [--headless/--no-headless]`
- Outputs under the job artifact directory:
  - `raw/form_original.html` – original HTML after network idle
  - `raw/form_schema.json` – JSON matching `docs/schemas/form_schema.json`
  - `raw/stage_1.png` – screenshot of the captured stage
  - `raw/capture_log.json` – minimal log (counts, notes)

Notes:
- The current capture groups everything into a single stage. Future iterations will split by sections/steps.
- Selectors favor `data-testid|data-test|data-qa|name|id` and fall back to generic selectors.
- Only visible `input`, `textarea`, and `select` are recorded; hidden inputs are skipped.

