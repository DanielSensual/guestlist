"""Muse Spark video understanding with schema-constrained JSON output."""

from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass
from pathlib import Path

from . import cache, files, pricing
from .client import check_model, client

DEFAULT_MODEL = "muse-spark-1.3"

EVENT_LOG_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["clip_summary", "people", "events"],
    "properties": {
        "clip_summary": {"type": "string"},
        "people": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "appearance", "first_seen_s"],
                "properties": {
                    "label": {"type": "string"},
                    "appearance": {"type": "string"},
                    "first_seen_s": {"type": "number"},
                },
            },
        },
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["t_start", "t_end", "people", "what", "why_it_matters", "score", "confidence"],
                "properties": {
                    "t_start": {"type": "number"},
                    "t_end": {"type": "number"},
                    "people": {"type": "array", "items": {"type": "string"}},
                    "what": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                    "score": {"type": "number"},
                    "confidence": {"type": "number"},
                },
            },
        },
    },
}

EVENT_LOG_DEVELOPER = (
    "You are the logging assistant for a professional event videographer. You watch raw event footage "
    "and write a precise shot log that an editor will use to cut a separate highlight film for every guest. "
    "Be literal and time-accurate; never invent people or actions you cannot see or hear."
)

EVENT_LOG_PROMPT = (
    "Log this clip.\n"
    "- people: every distinct person who is clearly visible, labelled P1, P2, ... in order of first appearance, "
    "with a short appearance description (clothing, hair, distinguishing features — no names, no guesses about "
    "identity) and the second they are first clearly visible.\n"
    "- events: the moments an editor would want, each with t_start/t_end in seconds from the start of the clip, "
    "the people labels involved, what happens, why it matters for that person's film, score 0-10 (how strong "
    "the moment is), and confidence 0-1 that the timing and people are right. Cover the whole clip; prefer "
    "several short precise moments over one long vague one.\n"
    "- clip_summary: two sentences."
)


@dataclass
class SparkResult:
    data: dict
    usage: dict
    usd: float
    seconds: float
    cached: bool
    meta: dict


def _usage_numbers(usage) -> tuple[int, int, int, int]:
    u = usage if isinstance(usage, dict) else usage.model_dump()
    cached = (u.get("input_tokens_details") or {}).get("cached_tokens", 0) or 0
    reasoning = (u.get("output_tokens_details") or {}).get("reasoning_tokens", 0) or 0
    return u["input_tokens"], cached, u["output_tokens"], reasoning


def video_json(video: str | Path, *, schema: dict, name: str, developer: str, prompt: str,
               model: str = DEFAULT_MODEL, effort: str = "medium", max_output_tokens: int = 16000,
               max_usd: float | None = None) -> SparkResult:
    """One video in, schema-constrained JSON out. Cached by (video hash, model, prompts, schema, effort)."""
    check_model(model)
    video = Path(video)
    k = cache.key(cache.sha256_file(video), model, developer, prompt, schema, effort)
    hit = cache.get("spark", k)
    if hit:
        return SparkResult(hit["data"], hit["usage"], hit["usd"], hit["seconds"], True, hit)

    if max_usd is not None:
        cache.guard(max_usd)
    file_id = files.upload(video)
    t0 = time.time()
    stream = client().responses.create(
        model=model,
        input=[
            {"role": "developer", "content": developer},
            {"role": "user", "content": [
                {"type": "input_video", "file_id": file_id},
                {"type": "input_text", "text": prompt},
            ]},
        ],
        text={"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}},
        reasoning={"effort": effort},
        max_output_tokens=max_output_tokens,
        stream=True,
    )
    headers = {k_: v for k_, v in stream.response.headers.items() if k_.lower().startswith("x-")}
    parts: list[str] = []
    final = None
    for event in stream:
        if event.type == "response.output_text.delta":
            parts.append(event.delta)
        elif event.type in ("response.completed", "response.incomplete"):
            final = event.response
        elif event.type in ("response.failed", "error"):
            raise RuntimeError(f"Spark request failed: {event}")
    seconds = time.time() - t0
    if final is None or final.usage is None:
        raise RuntimeError("Spark stream ended without usage")
    text = "".join(parts)
    usage = final.usage.model_dump()
    tin, tcached, tout, treason = _usage_numbers(usage)
    usd = pricing.token_cost(model, tin, tcached, tout)
    record = {"data": json.loads(text) if text else None, "text": text, "usage": usage, "usd": usd,
              "seconds": round(seconds, 2), "status": final.status, "file_id": file_id, "model": model,
              "effort": effort, "headers": headers}
    cache.put("spark", k, record)
    cache.charge("spark", model, usd, input_tokens=tin, cached_tokens=tcached, output_tokens=tout,
                 reasoning_tokens=treason, video=video.name, schema=name)
    if record["data"] is None:
        raise RuntimeError(f"Spark returned no JSON (status={final.status}); see cache record {k}")
    return SparkResult(record["data"], usage, usd, seconds, False, record)


def event_log(video: str | Path, **kw) -> SparkResult:
    return video_json(video, schema=EVENT_LOG_SCHEMA, name="event_log",
                      developer=EVENT_LOG_DEVELOPER, prompt=EVENT_LOG_PROMPT, **kw)


UNMARKED = "unmarked"

MARKED_PROMPT = (
    "Log this clip. Our tracker has outlined people and tagged them; each tag follows its person for the "
    "whole clip and has its own colour: {legend}. These tags are the ONLY labels you may use for people.\n"
    "- people: one entry per tag you actually see, labelled exactly as tagged, with a short appearance "
    "description of the person that tag is attached to (clothing, hair, distinguishing features — no names, "
    "no guesses about identity) and the second the tag first appears. Use \"" + UNMARKED + "\" for anyone "
    "important who has no tag.\n"
    "- events: the moments an editor would want, each with t_start/t_end in seconds from the start of the "
    "clip, the tags of the people involved, what happens, why it matters for that person's film, score 0-10 "
    "(how strong the moment is), and confidence 0-1 that the timing and tags are right. When tagged people "
    "overlap, go by the outline the tag sits on. Cover the whole clip; prefer several short precise moments "
    "over one long vague one.\n"
    "- clip_summary: two sentences."
)


def marked_schema(labels: list[str]) -> dict:
    """The event-log schema with person labels restricted to our tags (plus "unmarked")."""
    schema = copy.deepcopy(EVENT_LOG_SCHEMA)
    allowed = {"type": "string", "enum": [*labels, UNMARKED]}
    schema["properties"]["people"]["items"]["properties"]["label"] = allowed
    schema["properties"]["events"]["items"]["properties"]["people"]["items"] = dict(allowed)
    return schema


def marked_event_log(video: str | Path, legend: dict[str, str], **kw) -> SparkResult:
    """Event log over a marked proxy (`guestlist.burn`): Spark refers to people by our track tags."""
    text = ", ".join(f"{tag} = {colour} outline" for tag, colour in legend.items())
    return video_json(video, schema=marked_schema(list(legend)), name="marked_event_log",
                      developer=EVENT_LOG_DEVELOPER, prompt=MARKED_PROMPT.format(legend=text), **kw)


def count_video_tokens(video: str | Path, prompt: str = "Describe this clip.", model: str = DEFAULT_MODEL) -> int:
    """Input-token count for one video + a short prompt, via POST /v1/responses/input_tokens (no generation)."""
    check_model(model)
    k = cache.key(cache.sha256_file(video), model, "count", prompt)
    hit = cache.get("count", k)
    if hit:
        return hit["input_tokens"]
    file_id = files.upload(video)
    resp = client().post(
        "/responses/input_tokens",
        body={"model": model, "input": [{"role": "user", "content": [
            {"type": "input_video", "file_id": file_id}, {"type": "input_text", "text": prompt}]}]},
        cast_to=object,
    )
    n = int(resp["input_tokens"])
    cache.put("count", k, {"input_tokens": n, "raw": resp})
    return n


def count_text_tokens(prompt: str = "Describe this clip.", model: str = DEFAULT_MODEL) -> int:
    k = cache.key("text", model, "count", prompt)
    hit = cache.get("count", k)
    if hit:
        return hit["input_tokens"]
    resp = client().post("/responses/input_tokens",
                         body={"model": model, "input": [{"role": "user", "content": prompt}]}, cast_to=object)
    n = int(resp["input_tokens"])
    cache.put("count", k, {"input_tokens": n, "raw": resp})
    return n
