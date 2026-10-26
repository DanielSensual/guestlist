"""Meta Model API list prices (Standard mode), from dev.meta.ai/docs/pricing-rate-limits, 2026-10-26."""

from __future__ import annotations

# model -> (input, cached input, output) USD per 1M tokens
TOKEN_RATES = {
    "muse-spark-1.3": (1.25, 0.15, 4.25),
    "muse-spark-1.2": (1.25, 0.15, 4.25),
    "muse-spark-1.1": (1.25, 0.15, 4.25),
    "muse-wonder-1.0": (4.00, 0.20, 20.00),
}
SAM_VIDEO_PER_FRAME = 0.20 / 1000
SAM_IMAGE_EACH = 2.50 / 1000
SAM_MIN_FRAMES = 50
TRANSCRIBE_PER_SECOND = 0.18 / 3600
IMAGE_EACH = 0.01


def token_cost(model: str, input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    rate_in, rate_cached, rate_out = TOKEN_RATES[model]
    fresh = max(0, input_tokens - cached_tokens)
    return (fresh * rate_in + cached_tokens * rate_cached + output_tokens * rate_out) / 1e6


def sam_video_cost(frames: int) -> float:
    return max(frames, SAM_MIN_FRAMES) * SAM_VIDEO_PER_FRAME


def transcribe_cost(seconds: float) -> float:
    return seconds * TRANSCRIBE_PER_SECOND
