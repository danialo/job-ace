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
