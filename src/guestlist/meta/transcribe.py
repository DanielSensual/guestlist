"""Muse Voice Transcribe (file endpoint) with speaker diarization. Turn-level timestamps only."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import httpx

from . import cache, pricing
from .client import BASE_URL, api_key

MODEL = "muse-voice-transcribe-1.0"


def diarize(wav: str | Path, *, language_bias: list[str] | None = None) -> dict:
    """WAV (mono, 16-bit PCM, 16 or 24 kHz) -> {"transcript", "turns": [{startMs, endMs, transcript, speaker}], ...}."""
    wav = Path(wav)
    request = {"mode": "DIARIZATION", "model": MODEL, "audioEncoding": "WAV"}
    if language_bias:
        request["languageBias"] = language_bias
    k = cache.key(cache.sha256_file(wav), MODEL, request)
    hit = cache.get("transcribe", k)
    if hit:
        return hit["result"]
    t0 = time.time()
    with open(wav, "rb") as f:
        r = httpx.post(
            f"{BASE_URL}/asr/transcribe",
            params={"sessionId": f"guestlist-{uuid.uuid4().hex[:12]}"},
            headers={"Authorization": f"Bearer {api_key()}"},
            files={"request": (None, json.dumps(request), "application/json"),
                   "audio": (wav.name, f, "audio/wav")},
            timeout=600,
        )
    if r.status_code != 200:
        raise RuntimeError(f"transcribe HTTP {r.status_code}: {r.text[:500]}")
    result = r.json()
    seconds = (result.get("audioDurationMs") or 0) / 1000
    usd = pricing.transcribe_cost(seconds)
    cache.put("transcribe", k, {"result": result, "usd": usd, "seconds": round(time.time() - t0, 2)})
    cache.charge("transcribe", MODEL, usd, audio_seconds=seconds, audio=wav.name)
    return result
