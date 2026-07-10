# Job + Resume Pairing

Status: approved 2026-07-07

## Problem

The job description and the resume generated for it go together, but only one of them survives.

- **Generated resumes vanish.** The Tailor step writes intermediate markdown to `artifacts/job-<id>/derived/` (buried, never surfaced again) and `/export` renders the final PDF/DOCX but only streams it to the browser. After a reload the portal shows the job with no trace of the resume that was built for it — the user has to rebuild from scratch to re-export, and there is no record of what was actually sent to the employer.
- **Uploaded resumes are discarded.** `/upload-resume` and `/parse-resume` write the uploaded file to a temp path, extract blocks, and delete the file. Resume Intake keeps the blocks but not the resume.

## Requirements

1. **Per-job generated resumes.** Exporting a resume for a job persists it, attached to that job. Returning later, the user opens the job and sees JD + resume together: the tailored text, downloadable PDF/DOCX, and the ability to restore the tailor state (selected blocks, tailored overrides, template) to tweak and re-export without rebuilding.
2. **Versioning.** Every distinct generation is kept (v1, v2, ...); the job page shows the latest with older versions listed. Nothing is overwritten — the record of what was applied with is never lost.
3. **Uploaded resume storage.** Files uploaded in Resume Intake are stored as first-class uploaded resumes, listed and downloadable. Deliberately **not** attached to jobs — uploads are raw material, not refined output.

## Data Model

Two new tables, auto-created by `Base.metadata.create_all()` on restart — no column migrations on existing tables, so live (:3000), staging (:3001), and the :3002 instance pick them up by restart.

### `generated_resume`

One row per distinct resume generated for a job.

| column | type | purpose |
|---|---|---|
| `id` | int PK | |
| `job_posting_id` | FK job_posting, not null | the job this resume was generated for |
| `version` | int, not null | auto-increments per job (unique with job_posting_id) |
| `block_ids_json` | text | selected block IDs at export time |
| `overrides_json` | text | snapshot of per-block tailored text at export time (`{block_id: text}`) |
| `tailored` | bool | whether tailored overrides were used |
| `template` | string | template rendered with |
| `resume_text` | text | assembled full text, for display on the job page |
| `pdf_path` | text, nullable | rendered PDF under `artifacts/job-<id>/exports/` |
| `docx_path` | text, nullable | rendered DOCX under `artifacts/job-<id>/exports/` |
| `content_sha` | string | SHA256 of (block_ids + overrides + template), for version merging |
| `created_at` | datetime | |

**Version semantics.** On export, if `content_sha` matches the job's latest version, the export fills the missing format path on that row (exporting PDF then DOCX of identical content = one version with both files). Any content change creates a new version row. Rendered files are also registered in the existing `artifact` table (kind `resume_export_pdf` / `resume_export_docx`) — `generated_resume` is the index/state layer, artifacts remain the file ledger.

The overrides snapshot is copied into the row at export time. The mutable `derived/tailored_blocks.json` (overwritten per tailor run) is unchanged and remains the "current working tailor" for the job; the snapshot is what makes old versions restorable.

### `uploaded_resume`

One row per file uploaded in Resume Intake.

| column | type | purpose |
|---|---|---|
| `id` | int PK | |
| `filename` | string | original filename |
| `path` | text | stored file under `data_root/resumes/` |
| `sha256` | string | content hash |
| `size_bytes` | int | |
| `block_ids_json` | text, nullable | blocks extracted from this upload (filled at confirm time) |
| `created_at` | datetime | |

Re-uploading a byte-identical file (same `sha256`) reuses the existing row instead of creating a duplicate; the response says so. If blocks are then re-confirmed for a reused row, `block_ids_json` is overwritten with the latest confirmation — the row always reflects the most recent extraction of that file.

## Backend

### Changed endpoints

- **`POST /export`** — after rendering: write the file to `artifacts/job-<id>/exports/resume_v<N>.<ext>` via `ArtifactManager`, create/update the `generated_resume` row per the version semantics above, then stream the download as today. If persistence fails, the request fails (500) and no file is streamed — fail loud, no silent unrecorded downloads.
- **`POST /parse-resume`** — also persists the uploaded file (creating the `uploaded_resume` row with `block_ids_json` null) and returns an `upload_id` alongside the preview blocks.
- **`POST /confirm-resume-blocks`** — accepts optional `upload_id`; on save, writes the created block IDs into that row's `block_ids_json`.
- **`POST /upload-resume`** (direct path) — persists file + row + block links in one shot.
- **`GET /jobs/{id}`** — response gains `latest_resume`: `{version, created_at, template, has_pdf, has_docx}` or null, so the job page shows the pair in one call.

### New endpoints

- **`GET /jobs/{id}/resumes`** — version list: `[{id, version, created_at, template, tailored, has_pdf, has_docx, block_count}]`.
- **`GET /jobs/{id}/resumes/latest`** and **`GET /jobs/{id}/resumes/{version}`** — full detail of one version: `resume_text`, `block_ids`, `overrides`, `template`, `tailored`, available formats.
- **`GET /generated-resumes/{id}/download?format=pdf|docx`** — streams the stored file. 404 naming the missing path if the file is gone from disk.
- **`GET /uploaded-resumes`** — list: `[{id, filename, size_bytes, created_at, block_count}]`.
- **`GET /uploaded-resumes/{id}/download`** — streams the original file.

### Service layer

New `ResumeStoreService` (`backend/services/resume_store.py`) owning both tables: version allocation, content-sha merging, file placement, restore payload assembly. `/export` calls into it after `ExportService` renders; no rendering logic moves.

## Frontend

- **Job view (expanded card, extends the job-inspection-view surface):** a "Generated Resume" panel next to the JD sections — latest version's `resume_text`, PDF/DOCX download buttons, version history list, and a **Load in Tailor** button.
- **Tailor tab:** selecting a job that has saved resumes offers *"Load saved resume (v2, 2026-07-03)"* — restores block selection, tailored overrides, and template so the user tweaks and re-exports instead of rebuilding. After export, confirmation shows *"Saved as v3 on this job."*
- **Resume Intake:** a list of previously uploaded resumes (filename, date, blocks extracted, download link) above the upload control.

## Error Handling

- Download of a file missing from disk → 404 with the expected path in the message, not a crash.
- Restore when some saved block IDs have since been deleted → load the surviving blocks, warn explicitly which are missing (overrides for missing blocks are shown read-only in the warning so the text isn't lost).
- Export persistence failure → 500, no download, error surfaced in the UI.

## Testing

Service-level pytest coverage, all against an isolated tmp database and tmp data root (never the live DB — per the issue #3 hardening; snapshot the DB before any suite run regardless):

- export creates row + file; version increments on content change
- same-content export in the second format merges into the existing version row
- content change after export creates a new version, old row untouched
- upload persists file; identical re-upload reuses the row
- confirm links block IDs to the upload row
- restore payload correctness (blocks + overrides + template round-trip)
- restore with deleted blocks returns survivors + explicit missing list
- download endpoints: happy path and missing-file 404

## Rollout

Branch + PR (master ruleset: 1 approval + CI `test` check), tests + CI green, deploy by restart — tables self-create. Staging (:3001) first for a click-through before live.

## Relationship to Other Specs

- **`resume-object-model.md`**: orthogonal — it restructures how exporters render; this spec stores what they rendered. If `ResumeDocument` lands, `resume_text` stays the display text and the stored files remain renderer output.
- **`job-inspection-view.md`**: the Generated Resume panel is a new section of that expanded card, following its section pattern (decision-critical content visible, provenance collapsed).
