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


class SparkNoAnswer(RuntimeError):
    pass


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
    return _structured(k, [{"type": "input_video", "file_id": file_id}, {"type": "input_text", "text": prompt}],
                       schema=schema, name=name, developer=developer, model=model, effort=effort,
                       max_output_tokens=max_output_tokens, record={"file_id": file_id}, detail={"video": video.name})


def image_json(images: list[str | Path], *, schema: dict, name: str, developer: str, prompt: str,
               model: str = DEFAULT_MODEL, effort: str = "medium", max_output_tokens: int = 8000,
               max_usd: float | None = None) -> SparkResult:
    """Images in (inline data URLs), schema-constrained JSON out. Cached by (image hashes, model, prompts, schema)."""
    import base64

    check_model(model)
    images = [Path(p) for p in images]
    k = cache.key([cache.sha256_file(p) for p in images], model, developer, prompt, schema, effort, "image")
    hit = cache.get("spark", k)
    if hit:
        return SparkResult(hit["data"], hit["usage"], hit["usd"], hit["seconds"], True, hit)
    if max_usd is not None:
        cache.guard(max_usd)
    content = []
    for p in images:
        mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
        content.append({"type": "input_image",
                        "image_url": f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"})
    content.append({"type": "input_text", "text": prompt})
    return _structured(k, content, schema=schema, name=name, developer=developer, model=model, effort=effort,
                       max_output_tokens=max_output_tokens, record={}, detail={"images": [p.name for p in images]})


def _structured(k: str, content: list[dict], *, schema: dict, name: str, developer: str, model: str, effort: str,
                max_output_tokens: int, record: dict, detail: dict) -> SparkResult:
    """Stream one structured-output request, cache it under `k`, and charge the ledger."""
    t0 = time.time()
    stream = client().responses.create(
        model=model,
        input=[
            {"role": "developer", "content": developer},
            {"role": "user", "content": content},
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
              "seconds": round(seconds, 2), "status": final.status, "model": model,
              "effort": effort, "headers": headers, **record}
    cache.charge("spark", model, usd, input_tokens=tin, cached_tokens=tcached, output_tokens=tout,
                 reasoning_tokens=treason, schema=name, **detail)
    if record["data"] is None:  # e.g. reasoning used the whole output budget; never cache a non-answer
        raise SparkNoAnswer(f"Spark returned no JSON (status={final.status}, {treason} reasoning tokens)")
    cache.put("spark", k, record)
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


NONE = "none"

REID_DEVELOPER = (
    "You help a professional event videographer build the guest list for an event they filmed. You compare "
    "crops of people from dark, moving footage and say whether two crops show the same person. You judge only "
    "by what is visible (clothing, hair, accessories, build, anything they carry). You never name or try to "
    "identify anyone, and you say none when you are not sure."
)

REID_PROMPT = (
    "The top row (QUERY) shows one person in {n_query} frames from event footage. Below it are candidate people, "
    "each shown in a few frames under a letter. In every frame the person meant is the lit one with the thin white "
    "outline; the dimmed surroundings (often other people) are only context. Which candidate is the same person "
    "as QUERY?\n"
    "- match: the letter of the same person, or \"" + NONE + "\" if no candidate clearly is.\n"
    "- also_same: any other letters that are also the QUERY person (a tracker can split one person in two); "
    "usually empty.\n"
    "- confidence: 0-1 that match is right.\n"
    "- evidence: the visible details you compared, in one sentence."
)


def reid_schema(letters: list[str]) -> dict:
    return {
        "type": "object", "additionalProperties": False,
        "required": ["match", "also_same", "confidence", "evidence"],
        "properties": {
            "match": {"type": "string", "enum": [*letters, NONE]},
            "also_same": {"type": "array", "items": {"type": "string", "enum": letters}},
            "confidence": {"type": "number"},
            "evidence": {"type": "string"},
        },
    }


def same_person(sheet: str | Path, letters: list[str], n_query: int, **kw) -> SparkResult:
    """One re-identification sheet (`guestlist.roster.reid_sheet`) -> which lettered candidate is the query."""
    return image_json([sheet], schema=reid_schema(letters), name="same_person", developer=REID_DEVELOPER,
                      prompt=REID_PROMPT.format(n_query=n_query), **kw)


PERSON_MOMENTS_PROMPT = (
    "Our tracker has outlined and tagged people in this clip ({legend}). Log the moments that belong in {tag}'s "
    "own highlight film; {tag} is the {colour} outline.\n"
    "- moments: only times when {tag} is clearly visible, each with t_start/t_end in seconds from the start of "
    "this clip, what {tag} does, why it matters for {tag}'s film, score 0-10, confidence 0-1 that the timing and "
    "the person are right, and with: the tags of anyone sharing the moment. Prefer several short precise moments "
    "(2-6 s) over long vague ones; return an empty list if {tag} does nothing worth keeping.\n"
    "- summary: one sentence on {tag}'s part in this clip (appearance and what they do; no names, no guesses about "
    "identity)."
)


def person_moments_schema(labels: list[str]) -> dict:
    tag = {"type": "string", "enum": [*labels, UNMARKED]}
    moment = {
        "type": "object", "additionalProperties": False,
        "required": ["t_start", "t_end", "what", "why_it_matters", "score", "confidence", "with"],
        "properties": {"t_start": {"type": "number"}, "t_end": {"type": "number"}, "what": {"type": "string"},
                       "why_it_matters": {"type": "string"}, "score": {"type": "number"},
                       "confidence": {"type": "number"}, "with": {"type": "array", "items": tag}},
    }
    return {"type": "object", "additionalProperties": False, "required": ["summary", "moments"],
            "properties": {"summary": {"type": "string"}, "moments": {"type": "array", "items": moment}}}


def person_moments(video: str | Path, tag: str, legend: dict[str, str], **kw) -> SparkResult:
    """One guest's moments from a marked clip (`guestlist.burn`), with co-stars named by their tags."""
    text = ", ".join(f"{t} = {c} outline" for t, c in legend.items())
    return video_json(video, schema=person_moments_schema(list(legend)), name="person_moments",
                      developer=EVENT_LOG_DEVELOPER,
                      prompt=PERSON_MOMENTS_PROMPT.format(legend=text, tag=tag, colour=legend[tag]), **kw)


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
