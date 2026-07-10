"""Prompt Lab: tuning/scoring pipeline for the polish prompt.

Stores corpora, variants, and experiments as JSON under
data_root/prompt_lab/ (gitignored — the repo is public and corpora contain
real resume text). See specs/polish-prompt-lab.md.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from slugify import slugify
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models import models
from backend.services import polish_scorers
from backend.services.prompt_store import render_template, shipped_prompt_text

settings = get_settings()

SHIPPED_BASELINE = "shipped:default"


def is_enabled() -> bool:
    return bool(settings.debug_menu)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PromptLabService:
    def __init__(self, db: Session):
        self.db = db

    # -- storage helpers ------------------------------------------------

    @property
    def root(self) -> Path:
        return settings.data_root / "prompt_lab"

    def _dir(self, name: str) -> Path:
        d = self.root / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _next_numbered_id(self, dirname: str, prefix: str) -> str:
        pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)\.json$")
        highest = 0
        for f in self._dir(dirname).iterdir():
            m = pattern.match(f.name)
            if m:
                highest = max(highest, int(m.group(1)))
        return f"{prefix}-{highest + 1}"

    @staticmethod
    def _read(path: Path) -> Optional[Dict]:
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write(path: Path, payload: Dict) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # -- corpus ----------------------------------------------------------

    def snapshot_corpus(self) -> Dict:
        blocks = self.db.scalars(
            select(models.ResumeBlock).order_by(models.ResumeBlock.id)
        ).all()
        if not blocks:
            raise ValueError("No resume blocks to snapshot")
        corpus_id = self._next_numbered_id("corpus", "corpus")
        payload = {
            "id": corpus_id,
            "created_at": _now(),
            "blocks": [
                {
                    "block_id": b.id,
                    "category": b.category,
                    "text": b.text,
                    "job_title": b.job_title,
                    "company": b.company,
                }
                for b in blocks
            ],
        }
        self._write(self._dir("corpus") / f"{corpus_id}.json", payload)
        return payload

    def list_corpora(self) -> List[Dict]:
        out = []
        for f in sorted(self._dir("corpus").glob("corpus-*.json")):
            data = self._read(f)
            if data:
                out.append(
                    {
                        "id": data["id"],
                        "created_at": data["created_at"],
                        "block_count": len(data["blocks"]),
                    }
                )
        out.sort(key=lambda c: int(c["id"].split("-")[1]), reverse=True)
        return out

    def get_corpus(self, corpus_id: str) -> Optional[Dict]:
        return self._read(self._dir("corpus") / f"{corpus_id}.json")

    # -- variants ---------------------------------------------------------

    def create_variant(self, name: str, base: str) -> Dict:
        slug = slugify(name)
        if not slug:
            raise ValueError("Variant name produces an empty slug")
        path = self._dir("variants") / f"{slug}.json"
        if path.exists():
            raise ValueError(f"Variant '{slug}' already exists")
        base_variant = self.get_variant(base)
        if base_variant is None:
            raise ValueError(f"Unknown base variant: {base}")
        payload = {
            "name": slug,
            "base": base,
            "prompt_text": base_variant["prompt_text"],
            "created_at": _now(),
        }
        self._write(path, payload)
        return payload

    def list_variants(self) -> List[Dict]:
        out: List[Dict] = [
            {
                "name": SHIPPED_BASELINE,
                "prompt_text": shipped_prompt_text(),
                "read_only": True,
            }
        ]
        for f in sorted(self._dir("variants").glob("*.json")):
            data = self._read(f)
            if data:
                data["read_only"] = False
                out.append(data)
        return out

    def get_variant(self, name: str) -> Optional[Dict]:
        if name == SHIPPED_BASELINE:
            return {
                "name": SHIPPED_BASELINE,
                "prompt_text": shipped_prompt_text(),
                "read_only": True,
            }
        return self._read(self._dir("variants") / f"{slugify(name)}.json")

    def update_variant(self, name: str, prompt_text: str) -> Dict:
        if name == SHIPPED_BASELINE:
            raise ValueError("The shipped baseline is read-only")
        path = self._dir("variants") / f"{slugify(name)}.json"
        data = self._read(path)
        if data is None:
            raise ValueError(f"Variant not found: {name}")
        data["prompt_text"] = prompt_text
        self._write(path, data)
        return data

    def delete_variant(self, name: str) -> None:
        if name == SHIPPED_BASELINE:
            raise ValueError("The shipped baseline is read-only")
        path = self._dir("variants") / f"{slugify(name)}.json"
        if not path.is_file():
            raise ValueError(f"Variant not found: {name}")
        path.unlink()

    # -- experiments -------------------------------------------------------

    def create_experiment(self, variant_names: List[str], corpus_id: str) -> Dict:
        if len(variant_names) < 2:
            raise ValueError("An experiment needs at least two variants")
        for name in variant_names:
            if self.get_variant(name) is None:
                raise ValueError(f"Unknown variant: {name}")
        corpus = self.get_corpus(corpus_id)
        if corpus is None:
            raise ValueError(f"Corpus not found: {corpus_id}")

        exp_id = self._next_numbered_id("experiments", "exp")
        payload = {
            "id": exp_id,
            "created_at": _now(),
            "variants": list(variant_names),
            "corpus_id": corpus_id,
            "cells": [
                {"variant": v, "block_id": b["block_id"], "status": "pending"}
                for v in variant_names
                for b in corpus["blocks"]
            ],
            "results": {},
            "picks": {},
        }
        self._write(self._dir("experiments") / f"{exp_id}.json", payload)
        return payload

    def _default_llm(self):
        from backend.services.llm import OpenAIClient, get_llm_client

        client = get_llm_client(settings, task="tailoring")

        def runner(prompt: str) -> str:
            if isinstance(client, OpenAIClient):
                response = client.client.chat.completions.create(
                    model=client.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=2000,
                )
                return (response.choices[0].message.content or "").strip()
            # Stub provider mirrors the polish endpoint: no rewrite.
            marker = "SOURCE WORK EXPERIENCE ENTRY:\n"
            return prompt.split(marker, 1)[-1] if marker in prompt else prompt

        return runner, client.check_compliance

    def run_cell(
        self,
        exp_id: str,
        variant: str,
        block_id: int,
        llm_runner=None,
        checker=None,
    ) -> Dict:
        path = self._dir("experiments") / f"{exp_id}.json"
        exp = self._read(path)
        if exp is None:
            raise ValueError(f"Experiment not found: {exp_id}")
        if variant not in exp["variants"]:
            raise ValueError(f"Variant {variant} is not part of {exp_id}")
        corpus = self.get_corpus(exp["corpus_id"])
        block = next(
            (b for b in corpus["blocks"] if b["block_id"] == block_id), None
        )
        if block is None:
            raise ValueError(f"Block {block_id} is not in corpus {exp['corpus_id']}")

        if llm_runner is None or checker is None:
            default_runner, default_checker = self._default_llm()
            llm_runner = llm_runner or default_runner
            checker = checker or default_checker

        variant_data = self.get_variant(variant)
        prompt = render_template(
            variant_data["prompt_text"], block["text"], block.get("category")
        )

        cell: Dict = {"variant": variant, "block_id": block_id}
        try:
            output = llm_runner(prompt)
            cell["output"] = output
            cell["error"] = None
            cell["scores"] = polish_scorers.score_output(
                block["text"], output, block, checker
            )
        except Exception as exc:
            cell["output"] = None
            cell["error"] = str(exc)
            cell["scores"] = None

        exp["results"][f"{variant}::{block_id}"] = cell
        for c in exp["cells"]:
            if c["variant"] == variant and c["block_id"] == block_id:
                c["status"] = "error" if cell["error"] else "done"
        self._write(path, exp)
        return cell

    def record_pick(self, exp_id: str, block_id: int, variant: str) -> Dict:
        path = self._dir("experiments") / f"{exp_id}.json"
        exp = self._read(path)
        if exp is None:
            raise ValueError(f"Experiment not found: {exp_id}")
        if variant not in exp["variants"]:
            raise ValueError(f"Variant {variant} is not part of {exp_id}")
        exp["picks"][str(block_id)] = variant
        self._write(path, exp)
        return exp["picks"]

    def get_experiment(self, exp_id: str) -> Optional[Dict]:
        exp = self._read(self._dir("experiments") / f"{exp_id}.json")
        if exp is None:
            return None
        exp["rollups"] = self._rollups(exp)
        return exp

    def list_experiments(self) -> List[Dict]:
        out = []
        for f in sorted(self._dir("experiments").glob("exp-*.json")):
            e = self._read(f)
            if e:
                out.append(
                    {
                        "id": e["id"],
                        "created_at": e["created_at"],
                        "variants": e["variants"],
                        "corpus_id": e["corpus_id"],
                        "cells_total": len(e["cells"]),
                        "cells_run": sum(
                            1 for c in e["cells"] if c["status"] != "pending"
                        ),
                    }
                )
        out.sort(key=lambda e: int(e["id"].split("-")[1]), reverse=True)
        return out

    @staticmethod
    def _rollups(exp: Dict) -> Dict:
        rollups: Dict = {}
        for v in exp["variants"]:
            cells = [
                c for k, c in exp["results"].items() if k.startswith(f"{v}::")
            ]
            scored = [c for c in cells if c.get("scores")]
            fillers = [c["scores"]["filler_count"] for c in scored]
            deltas = [abs(c["scores"]["length_delta"]) for c in scored]
            rollups[v] = {
                "cells_run": len(cells),
                "errors": sum(1 for c in cells if c.get("error")),
                "fabrication_failures": sum(
                    1 for c in scored if c["scores"]["fabrication"]["ok"] is False
                ),
                "fabrication_unchecked": sum(
                    1 for c in scored if c["scores"]["fabrication"]["ok"] is None
                ),
                "mean_filler": round(sum(fillers) / len(fillers), 2) if fillers else 0,
                "mean_abs_length_delta": round(sum(deltas) / len(deltas), 3)
                if deltas
                else 0,
                "structure_breaks": sum(
                    1
                    for c in scored
                    if not c["scores"]["structure"]["bullets_preserved"]
                    or not c["scores"]["structure"]["header_preserved"]
                ),
                "picks": sum(1 for p in exp["picks"].values() if p == v),
            }
        return rollups
