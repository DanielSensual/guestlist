"""Content-addressed disk cache for API responses, plus a spend ledger with a hard budget stop.

Keys are sha256 over (source file hash, model, prompt, options), so re-running any
analysis on the same footage costs nothing.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("GUESTLIST_HOME", Path(__file__).resolve().parents[3]))
CACHE_DIR = Path(os.environ.get("GUESTLIST_CACHE", ROOT / ".cache"))
LEDGER = CACHE_DIR / "spend.jsonl"
BUDGET_USD = float(os.environ.get("GUESTLIST_BUDGET_USD", "115"))
_LOCK = threading.Lock()  # windowed SAM runs requests on worker threads; index and ledger writes go one at a time


class BudgetExceeded(RuntimeError):
    pass


def key(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def sha256_file(path: str | Path) -> str:
    """Hash a file once; remember it by (path, size, mtime) so big proxies aren't re-read."""
    path = Path(path).resolve()
    st = path.stat()
    index_path = CACHE_DIR / "sha256-index.json"
    stamp = f"{path}|{st.st_size}|{st.st_mtime_ns}"
    with _LOCK:
        index = json.loads(index_path.read_text()) if index_path.exists() else {}
        if stamp in index:
            return index[stamp]
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    with _LOCK:
        index = json.loads(index_path.read_text()) if index_path.exists() else {}
        index[stamp] = h.hexdigest()
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps(index, indent=1))
    return index[stamp]


def get(namespace: str, k: str) -> dict | None:
    p = CACHE_DIR / namespace / f"{k}.json"
    return json.loads(p.read_text()) if p.exists() else None


def put(namespace: str, k: str, value: dict) -> None:
    p = CACHE_DIR / namespace / f"{k}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=1))


def drop(namespace: str, k: str) -> None:
    (CACHE_DIR / namespace / f"{k}.json").unlink(missing_ok=True)


def spent() -> float:
    if not LEDGER.exists():
        return 0.0
    return sum(json.loads(line)["usd"] for line in LEDGER.read_text().splitlines() if line.strip())


def charge(what: str, model: str, usd: float, **detail: Any) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, open(LEDGER, "a") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "what": what, "model": model,
                            "usd": round(usd, 6), **detail}) + "\n")


def guard(estimate_usd: float = 0.0) -> None:
    """Refuse a call that would push total spend past the hard stop."""
    if spent() + estimate_usd > BUDGET_USD:
        raise BudgetExceeded(f"spent ${spent():.2f} + est ${estimate_usd:.2f} > hard stop ${BUDGET_USD:.2f}")
