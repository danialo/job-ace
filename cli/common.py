from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

API_BASE_URL = os.getenv("JOB_ACE_API_URL", "http://127.0.0.1:8000")


def post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{API_BASE_URL}{path}"
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


def get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"{API_BASE_URL}{path}"
    with httpx.Client(timeout=30.0) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        return response.json()


def dump_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
