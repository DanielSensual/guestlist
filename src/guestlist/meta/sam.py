"""SAM 3.1 video segmentation and tracking.

Two prompt kinds (never mixed in one request):
- concept: one short noun phrase, e.g. "person" — every match, ids chosen by the model
- objects: box/point prompts on chosen frames, ids chosen by us (`build_objects_prompt`)

Raw output text is cached and parsed offline: boxes/ids/confidence with a regex, masks in bulk
through Meta's JS decoder (`decode_masks`, `mask_fills`).

One request hands out at most `MAX_IDS` object ids (Day-2 finding); long or crowded clips go
through `guestlist.windows`.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from meta_sam_parser import (
    FramePrompt,
    PromptBox,
    PromptObject,
    PromptPoint,
    SegmentationMask,
    build_object_prompt,
    decode_mask_to_raster,
)

from . import cache, files, pricing
from .client import client

MODEL = "sam-3.1"
MAX_IDS = 16  # a concept pass stops assigning new ids after 16, however long the clip


@dataclass
class Detection:
    frame: int
    object_id: str
    box: tuple[int, int, int, int]  # left, top, right, bottom — right/bottom exclusive, source pixels
    confidence: float | None = None
    mask: SegmentationMask | None = None

    def mask_array(self) -> np.ndarray | None:
        """Binary mask over `box` (rows = box height, cols = box width). Slow (~1 s); prefer `decode_masks`."""
        if self.mask is None:
            return None
        raster = decode_mask_to_raster(self.mask)
        return fit_to_box(np.frombuffer(raster, dtype=np.uint8).reshape(self.mask.height, self.mask.width), self.box)


def fit_to_box(raster: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    """SAM caps a mask raster's long side (1024 px seen); scale it back to cover the whole box."""
    bw, bh = box[2] - box[0], box[3] - box[1]
    if raster.shape == (bh, bw):
        return raster
    return cv2.resize(raster, (bw, bh), interpolation=cv2.INTER_NEAREST)


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


_FRAME = re.compile(r"<(\d+)f>")
_RECORD = re.compile(r"(?:^|,)(\d+)<\|box;([^|]*)\|><\|mask;([^|]*)\|>")
_ENCODING = {"~": "lossless", "!": "one_bit"}


def _fields(token: str) -> dict[str, str]:
    head, _, data = token.partition("data=")
    out = dict(kv.split("=", 1) for kv in head.strip(";").split(";") if "=" in kv)
    if data:
        out["data"] = data
    return out


def parse(text: str) -> tuple[list[Detection], tuple[int, int] | None]:
    """Parse SAM's per-frame token text into detections. Fast: masks stay encoded until `mask_array()`.

    `meta_sam_parser` strictly decodes every mask while parsing (~1 s per one_bit mask in pure
    Python), which makes a 60 s clip take ~30 min. Boxes, ids and confidence are all tracking
    needs, so we read those with a regex and decode masks lazily with the official decoder.
    """
    dets: list[Detection] = []
    size: tuple[int, int] | None = None
    for line in text.splitlines():
        m = _FRAME.match(line)
        if not m:
            continue
        frame = int(m.group(1))
        for oid, box_tok, mask_tok in _RECORD.findall(line[m.end():]):
            b = _fields(box_tok)
            if size is None:
                size = (int(b["w"]), int(b["h"]))
            mk = _fields(mask_tok)
            h, w, payload = mk["data"].split(",", 2)
            mask = SegmentationMask(encoding=_ENCODING.get(payload[:1], "lossless"), payload=payload,
                                    width=int(w), height=int(h))
            conf = b.get("c") or mk.get("c")
            dets.append(Detection(frame, oid, (int(b["x1"]), int(b["y1"]), int(b["x2"]) + 1, int(b["y2"]) + 1),
                                  float(conf) if conf is not None else None, mask))
    return dets, size


NODE_DECODER = Path(__file__).resolve().parents[3] / "tools" / "sam-decode" / "decode.mjs"


def rle_counts(s: str) -> list[int]:
    """COCO compressed-RLE string -> run lengths (pycocotools' rleFrString)."""
    counts: list[int] = []
    p = 0
    while p < len(s):
        x, k, more = 0, 0, True
        while more:
            c = ord(s[p]) - 48
            x |= (c & 0x1F) << (5 * k)
            more = bool(c & 0x20)
            p += 1
            k += 1
            if not more and (c & 0x10):
                x |= -1 << (5 * k)
        if len(counts) > 2:
            x += counts[-2]
        counts.append(x)
    return counts


def rle_to_array(rle: dict) -> np.ndarray:
    """COCO RLE {size: [h, w], counts} (column-major) -> (h, w) uint8 array."""
    h, w = rle["size"]
    counts = rle_counts(rle["counts"]) if isinstance(rle["counts"], str) else list(rle["counts"])
    values = np.arange(len(counts)) % 2
    flat = np.repeat(values.astype(np.uint8), counts)
    return flat.reshape(w, h).T.copy()


def rle_area(rle: dict) -> float:
    """Fraction of the raster that is mask, straight from the run lengths (runs alternate 0s, 1s, ...)."""
    h, w = rle["size"]
    counts = rle_counts(rle["counts"]) if isinstance(rle["counts"], str) else list(rle["counts"])
    return sum(counts[1::2]) / (h * w) if h * w else 0.0


def _node_rles(dets: list[Detection]) -> dict[tuple[int, str], dict]:
    """(frame, id) -> COCO RLE, decoded through Meta's JS decoder (~12 ms/mask vs ~1 s in Python)."""
    import json
    import subprocess

    jobs = "\n".join(json.dumps({"key": f"{d.frame}:{d.object_id}", "encoding": d.mask.encoding,
                                 "payload": d.mask.payload, "width": d.mask.width, "height": d.mask.height})
                     for d in dets if d.mask is not None)
    out = subprocess.run(["node", str(NODE_DECODER)], input=jobs, capture_output=True, text=True, check=True)
    rles: dict[tuple[int, str], dict] = {}
    for line in out.stdout.splitlines():
        row = json.loads(line)
        if "error" in row:
            raise RuntimeError(f"mask {row['key']}: {row['error']}")
        frame, oid = row["key"].split(":")
        rles[(int(frame), oid)] = row["rle"]
    return rles


def decode_masks(dets: list[Detection]) -> dict[tuple[int, str], np.ndarray]:
    """Decode many masks at once; each comes back scaled over its full box."""
    boxes = {(d.frame, d.object_id): d.box for d in dets}
    return {k: fit_to_box(rle_to_array(rle), boxes[k]) for k, rle in _node_rles(dets).items()}


def mask_fills(dets: list[Detection]) -> dict[tuple[int, str], float]:
    """(frame, id) -> mask area / box area. No rasters are built, so this is cheap enough to sample a clip."""
    return {k: rle_area(rle) for k, rle in _node_rles(dets).items()}


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
