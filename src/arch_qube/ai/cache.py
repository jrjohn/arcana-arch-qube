"""Cache AI analysis results by file content hash."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any

CACHE_DIR = Path(".arch-qube-cache")


def get_file_hash(file_path: Path) -> str:
    content = file_path.read_bytes()
    return hashlib.sha256(content).hexdigest()[:16]


def get_cached(rule_id: str, file_hash: str) -> dict | None:
    cache_file = CACHE_DIR / f"{rule_id}_{file_hash}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    return None


def set_cached(rule_id: str, file_hash: str, result: dict) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{rule_id}_{file_hash}.json"
    cache_file.write_text(json.dumps(result, ensure_ascii=False))


def clear_cache() -> None:
    if CACHE_DIR.exists():
        for f in CACHE_DIR.glob("*.json"):
            f.unlink()
