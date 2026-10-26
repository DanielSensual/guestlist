"""SAM 3.1 video segmentation and tracking.

Two prompt kinds (never mixed in one request):
- concept: one short noun phrase, e.g. "person" — every match, ids chosen by the model
- objects: box/point prompts on chosen frames, ids chosen by us (`build_objects_prompt`)

Raw output text is cached and parsed offline with Meta's own `meta_sam_parser`.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from meta_sam_parser import (
    CompletedOutcome,
    FramePrompt,
    PromptBox,
    PromptObject,
    PromptPoint,
    SegmentationMask,
    build_object_prompt,
    decode_mask_to_raster,
    video_segmentation_format,
)

from . import cache, files, pricing
from .client import client

MODEL = "sam-3.1"


@dataclass
class Detection:
    frame: int
    object_id: str
    box: tuple[int, int, int, int]  # left, top, right, bottom — right/bottom exclusive, source pixels
    confidence: float | None = None
    mask: SegmentationMask | None = None

    def mask_array(self) -> np.ndarray | None:
        """Binary mask cropped to `box` (rows = box height, cols = box width)."""
        if self.mask is None:
            return None
        raster = decode_mask_to_raster(self.mask)
        return np.frombuffer(raster, dtype=np.uint8).reshape(self.mask.height, self.mask.width)


@dataclass
class SamResult:
    text: str
    detections: list[Detection]
    frame_size: tuple[int, int] | None  # (w, h) as SAM reported it
    frames_billed: int
    usd: float
    seconds: float
    cached: bool
    meta: dict = field(default_factory=dict)

    def tracks(self) -> dict[str, list[Detection]]:
        out: dict[str, list[Detection]] = defaultdict(list)
        for d in sorted(self.detections, key=lambda d: d.frame):
            out[d.object_id].append(d)
        return dict(out)


def parse(text: str) -> tuple[list[Detection], tuple[int, int] | None]:
    """Parse SAM's per-frame token text into detections (box + mask paired by frame and id)."""
    parser = video_segmentation_format().create_parser()
    parser.push(text, emit=False)
    result = parser.finish(CompletedOutcome()).result
    by_key: dict[tuple[int, str], Detection] = {}
    for rec in result.records:
        if rec.kind not in ("box", "mask"):
            continue
        k = (rec.frame.frame_index, rec.object_id)
        if rec.kind == "box":
            by_key[k] = Detection(k[0], k[1], (rec.left, rec.top, rec.right, rec.bottom), rec.confidence)
        else:
            det = by_key.setdefault(k, Detection(k[0], k[1], (rec.bounds.left, rec.bounds.top,
                                                               rec.bounds.right, rec.bounds.bottom)))
            det.mask = rec.mask
            if det.confidence is None:
                det.confidence = rec.confidence
    size = _frame_size(text)
    return list(by_key.values()), size


def _frame_size(text: str) -> tuple[int, int] | None:
    i = text.find(";w=")
    if i < 0:
        return None
    w = int(text[i + 3:text.index(";", i + 3)])
    j = text.find(";h=", i)
    end = min(x for x in (text.find(";", j + 3), text.find("|", j + 3)) if x > 0)
    return w, int(text[j + 3:end])


def build_objects_prompt(size: tuple[int, int], boxes: dict[int, tuple[int, int, tuple[int, int, int, int]]]) -> str:
    """{object_id: (frame, (left, top, right, bottom))} -> SAM box-prompt text. `size` is (w, h) as displayed."""
    objects = [PromptObject(id=oid, prompts=[FramePrompt(frame=frame, box=PromptBox(*box))])
               for oid, (frame, box) in boxes.items()]
    return build_object_prompt(size=size, objects=objects)


def build_points_prompt(size: tuple[int, int], points: dict[int, tuple[int, list[tuple[int, int, str]]]]) -> str:
    """{object_id: (frame, [(x, y, "positive"|"negative"), ...])} -> SAM point-prompt text."""
    objects = [PromptObject(id=oid, prompts=[FramePrompt(frame=frame, points=[PromptPoint(x, y, label=lab)
                                                                              for x, y, lab in pts])])
               for oid, (frame, pts) in points.items()]
    return build_object_prompt(size=size, objects=objects)


def segment_video(video: str | Path, prompt: str, *, direction: str | None = None,
                  include_confidence: bool = True, one_bit: bool = True,
                  max_usd: float | None = None) -> SamResult:
    """Run SAM 3.1 over a proxy clip. `prompt` is a noun phrase or object-prompt text."""
    video = Path(video)
    metadata = {"include_confidence": "true" if include_confidence else "false"}
    if one_bit:
        metadata["mask_encoding"] = "one_bit"
    if direction:
        metadata["propagation_direction"] = direction
    k = cache.key(cache.sha256_file(video), MODEL, prompt, metadata)
    hit = cache.get("sam", k)
    if hit:
        dets, size = parse(hit["text"])
        return SamResult(hit["text"], dets, size, hit["frames_billed"], hit["usd"], hit["seconds"], True, hit)

    if max_usd is not None:
        cache.guard(max_usd)
    file_id = files.upload(video)
    t0 = time.time()
    parts: list[str] = []
    usage = None
    headers: dict = {}
    stream = client().responses.create(
        model=MODEL,
        input=[{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_video", "file_id": file_id},
        ]}],
        metadata=metadata,
        stream=True,
    )
    headers = {k_: v for k_, v in stream.response.headers.items() if k_.lower().startswith("x-")}
    first_frame_at = None
    for event in stream:
        if event.type == "response.output_text.delta":
            if first_frame_at is None:
                first_frame_at = time.time() - t0
            parts.append(event.delta)
        elif event.type == "response.completed":
            usage = event.response.usage
        elif event.type in ("response.failed", "error"):
            raise RuntimeError(f"SAM request failed: {event}")
    seconds = time.time() - t0
    text = "".join(parts)
    frames = int(getattr(usage, "video_frames_processed", None) or (usage.model_extra or {}).get("video_frames_processed", 0)) if usage else 0
    usd = pricing.sam_video_cost(frames)
    record = {"text": text, "frames_billed": frames, "usd": usd, "seconds": round(seconds, 2),
              "first_frame_seconds": round(first_frame_at or 0, 2), "file_id": file_id, "prompt": prompt,
              "metadata": metadata, "headers": headers,
              "usage": usage.model_dump() if usage is not None else None}
    cache.put("sam", k, record)
    cache.charge("sam", MODEL, usd, frames=frames, video=video.name, prompt=prompt[:80])
    dets, size = parse(text)
    return SamResult(text, dets, size, frames, usd, seconds, False, record)
