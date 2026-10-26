"""One OpenAI-SDK client pointed at the Meta Model API."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from openai import OpenAI

BASE_URL = "https://api.meta.ai/v1"
KEY_FILE = Path.home() / ".config" / "ghostai" / "meta-api.env"


def api_key() -> str:
    """MODEL_API_KEY from the environment, else from the private key file. Never from the repo."""
    key = os.environ.get("MODEL_API_KEY", "").strip()
    if not key and KEY_FILE.exists():
        for line in KEY_FILE.read_text().splitlines():
            if line.startswith("MODEL_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("'\"")
    if not key:
        raise RuntimeError(f"MODEL_API_KEY is not set and {KEY_FILE} has none")
    return key


@lru_cache(maxsize=1)
def client() -> OpenAI:
    return OpenAI(base_url=BASE_URL, api_key=api_key(), timeout=900, max_retries=2)


def check_model(model: str) -> str:
    """Contributor-mode model IDs license Meta to train on what we send. Footage never goes there."""
    if model.endswith("-contributor"):
        raise ValueError(f"refusing contributor-mode model {model!r}: it would license the footage for training")
    return model
