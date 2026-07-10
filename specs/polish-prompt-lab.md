# Polish Prompt Lab

Status: approved 2026-07-10

## Problem

The polish prompt (issue #5) was made so conservative after the hallucination fix that its output is bland — and there is no way to test whether a prompt change helps or hurts. The prompt is an inline string in `backend/api/app.py`, invisible to review, and the only evaluation is polishing your real resume and squinting. Prompt changes need a repeatable loop: run variants against the same real blocks, score the outputs, compare side by side.

## Decisions (owner, 2026-07-10)

- **Scoring**: automatic scores rank candidates and catch regressions; the owner's side-by-side pick is the recorded verdict.
- **Corpus**: snapshots of real blocks stored under the instance's data root, gitignored — the repo is public, resume text never enters git. Each instance builds its own corpus.
- **Variants**: shipped prompts are files in the repo; experiment variants are created and edited in the debug menu and stored locally. Promoting a winner to the shipped prompt is a normal PR.
- **Interface**: a debug menu ("Prompt Lab") in the web UI, enabled by a config tunable only.

## 1. Prompts become files

- `backend/prompts/polish/default.txt` holds the current shipped prompt verbatim, with `{block_text}` and `{category}` placeholders.
- A loader (`backend/services/prompt_store.py`) resolves the prompt for a block: `backend/prompts/polish/<category>.txt` if present, else `default.txt`. This is the hook for per-category prompts later; only `default.txt` ships now.
- `POST /blocks/{id}/polish` reads its prompt through the loader. Behavior today is byte-identical to the inline string.

## 2. Prompt Lab service and storage

New `backend/services/prompt_lab.py`. All writes go under `data_root/prompt_lab/` (gitignored):

```
prompt_lab/
  corpus/corpus-<n>.json          # [{block_id, category, text, job_title, company}]
  variants/<slug>.json            # {name, base, prompt_text, created_at}
  experiments/exp-<n>.json        # {variants, corpus, results, picks, created_at}
```

Operations:

- `snapshot_corpus()` — copy current resume blocks into a new numbered corpus file.
- `list_corpora()`, `get_corpus(id)`.
- `create_variant(name, base)` — clone the shipped prompt (or another variant) into an editable local variant; `update_variant`, `list_variants`, `delete_variant`. The shipped prompt appears in listings as read-only baseline `shipped:default`.
- `run_experiment(variant_names, corpus_id)` — each variant × each corpus block through the same LLM call the real polish uses (tailoring model, temp 0.3). Results are written incrementally; a per-cell LLM failure records `{error}` for that cell and continues.
- `record_pick(experiment_id, block_id, variant_name)` — the owner's verdict per block.
- `get_experiment(id)` — results plus score rollups per variant.

## 3. Auto-scorers

Computed per output cell at run time, stored in the experiment file:

| scorer | signal |
|---|---|
| `fabrication` | existing `check_compliance` against the source block; failure is flagged prominently — the one non-negotiable score |
| `filler_count` | hits against the banned-filler list ("results-driven", "dynamic", "passionate", "team player", …) |
| `length_delta` | % length change vs original; catches bloat and gutting |
| `structure` | bullet count preserved; first line intact for experience blocks with headers |

Rollup per variant: fabrication failures (count), mean filler, mean |length_delta|, structure breaks, and owner picks won. Auto-scores order candidates; picks decide.

## 4. API and gating

New setting `debug_menu: bool = False` (`JOB_ACE_DEBUG_MENU`). Routes under `/prompt-lab/*`:

- `GET /prompt-lab/status` — enabled check (also how the FE decides to show the nav item)
- `POST /prompt-lab/corpus` (snapshot), `GET /prompt-lab/corpus`
- `GET/POST/PUT/DELETE /prompt-lab/variants[/{name}]`
- `POST /prompt-lab/experiments` (run), `GET /prompt-lab/experiments[/{id}]`
- `POST /prompt-lab/experiments/{id}/picks` — `{block_id, variant}`

When `debug_menu` is false every `/prompt-lab/*` route returns 404 and the UI renders nothing. Staging runs with the tunable on; live and the :3002 instance leave it off.

## 5. UI

Sidebar item "🧪 Prompt Lab" at the bottom, rendered only when `/prompt-lab/status` says enabled. One view, three panels:

- **Corpus** — "Snapshot current blocks" button; list of snapshots (id, date, block count).
- **Variants** — list with the shipped baseline read-only; Clone → textarea editor → Save.
- **Experiments** — select 2+ variants and a corpus → Run (button shows `Running m/n…` progress like Polish All) → results: a score table (variant × scorer rollups) and per-block side-by-side outputs with the polish review's diff highlighting against the original, a radio pick per block, and a running picks tally. Fabrication failures get a red banner on the cell.

## 6. Error handling

- Per-cell LLM errors are recorded and shown as failed cells; the experiment completes.
- Re-running an experiment with the same variants+corpus creates a new experiment (no mutation of past results).
- Corpus snapshot with zero blocks → 400 with a clear message.
- Variant names are slugified; collisions rejected with 409.
- Deleting a variant leaves past experiment files intact (they embed the prompt text used).

## 7. Testing

Service-level pytest with the stub LLM client, isolated tmp data root (per issue #3 discipline — snapshot the DB before any suite run regardless):

- prompt loader: category file wins over default; missing files fall back; polish endpoint output identical to the previous inline prompt
- corpus snapshot round-trip; empty-DB 400
- variant CRUD incl. name collision and shipped-baseline read-only
- experiment result shape; per-cell failure recorded without aborting
- each scorer against crafted outputs: fabricated metric, filler-laden, gutted length, dropped bullets
- gating: all `/prompt-lab/*` routes 404 when the tunable is off
- pick recording and rollup math

## 8. Rollout

Branch + PR (CI `test` check), merge, staging restart with `JOB_ACE_DEBUG_MENU=true` added to its systemd env. First experiment — shipped prompt vs. a de-neutered draft vs. owner edits, on a snapshot of the real blocks — is the acceptance test. Its winner is promoted to `backend/prompts/polish/default.txt` (or per-category files) in the PR that closes #5.

## Relationship to other work

- **Issue #5**: this pipeline is the instrument; the prompt fix that closes #5 is its first product.
- **Polish All (PR #21/#22)**: unchanged; reuses its diff-highlight rendering in experiment results.
- **Gap engine (parked)**: orthogonal — the lab tunes wording quality; the gap engine addresses missing content. Corpus snapshots may later serve as gap-engine test data.
