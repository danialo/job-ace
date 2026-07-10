# Task 8 – Merge-Blocker Fixes Report

## What Changed

### Finding 1 (Critical) – Concurrent `run_cell` lost results

**Root cause:** `run_cell` did an unlocked read-modify-write of the experiment JSON.
FastAPI dispatches sync handlers in a thread pool, so two concurrent cell POSTs could
both read the same stale file, each write its own result, and one clobber the other.

**Fix in `backend/services/prompt_lab.py`:**

1. Added `import fcntl`, `import os`, and `from contextlib import contextmanager`.
2. Added `_exclusive(self, path)` context manager that uses `os.open(..., O_CREAT|O_RDWR)`
   (not `open(..., "w")` which truncates the inode) so that all callers compete on the
   same inode and `fcntl.flock(LOCK_EX)` correctly serialises them.
3. In `run_cell`: the slow LLM call runs **outside** the lock. Only the final
   read-merge-write is wrapped in `_exclusive`; inside the lock the file is re-read
   fresh, the cell result applied, and the file written.
4. In `record_pick`: the whole read-modify-write is wrapped in `_exclusive` (fast
   operation; no LLM call to avoid serialising).

**Why `open(lock_path, "w")` was wrong:** "w" mode truncates the file on every open,
creating a new inode for each thread. Two threads then hold flocks on different inodes,
so there is no mutual exclusion. `O_CREAT|O_RDWR` creates the file if absent but never
truncates it; all threads open the same inode.

### Finding 2 (Important) – Experiments must embed prompt text

**Root cause:** `create_experiment` only stored variant *names*; `run_cell` re-read the
live variant file at run time. Editing or deleting a variant after experiment creation
could silently misattribute results to a different prompt.

**Fix:** `create_experiment` now snapshots every variant's prompt text at creation time:

```python
"prompts": {name: self.get_variant(name)["prompt_text"] for name in variant_names},
```

`run_cell` renders from `exp["prompts"][variant]` instead of calling `get_variant`.

### Finding 3 (Important) – `run_cell` on deleted variant → 500

**Fixed for free by Finding 2:** `run_cell` no longer calls `get_variant` at all, so
a deleted variant cannot raise `TypeError`. A defensive check for experiments created
before this change raises a clear `ValueError` instead of a cryptic traceback:

```python
if variant not in exp.get("prompts", {}):
    raise ValueError(
        f"Experiment {exp_id} has no embedded prompt for variant {variant} "
        "(created before prompt-snapshot support)"
    )
```

## Tests Added (appended to `tests/test_prompt_lab.py`)

| Test | What it proves |
|------|---------------|
| `test_concurrent_run_cell_no_clobber` | 4 cells via `ThreadPoolExecutor(max_workers=2)` with 50 ms sleep; asserts all 4 keys present and no cell status = pending |
| `test_embedded_prompt_snapshot_isolates_variant_changes` | Creates experiment, edits variant, runs cell — asserts output contains ORIGINAL prompt text |
| `test_run_cell_on_deleted_variant_uses_snapshot` | Deletes variant after experiment creation, runs its cell — no exception, result persisted |

## Test Evidence

```
# Targeted:
.venv/bin/python -m pytest tests/test_prompt_lab.py tests/test_api.py -v
→ 48 passed in 2.89s

# Full suite:
.venv/bin/python -m pytest tests/
→ 229 passed, 17 deselected, 1 warning in 5.39s
```

## Files Changed

- `backend/services/prompt_lab.py` – `_exclusive` CM, embedded prompts in
  `create_experiment`, locked write path in `run_cell` and `record_pick`
- `tests/test_prompt_lab.py` – 3 new tests appended
