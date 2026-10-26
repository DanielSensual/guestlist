"""Person tracks per clip, with the signals the review queue routes on.

A Track is one stitched SAM id in one clip: its box on every frame it is seen, and how much to
trust it. SAM's confidence is one number per object per request (Day-1 finding 3), so per-frame
trust comes from geometry: gaps, sudden jumps (a likely id swap), clipping at the frame edge and
how much of its box the mask fills.

Tracks too short or too small to be a guest are kept as crowd. Crowd never gets a film, but the
consent engine must still be able to find and blur them, so nothing is thrown away. This split is
per track and provisional: the roster re-decides per person once fragments are merged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .meta import sam

MIN_GUEST_SECONDS = 2.0  # Day-2 club test: at 1 s / 1% two thirds of a packed floor became "guests"
MIN_GUEST_AREA = 0.02    # median box area as a fraction of the frame
LOW_CONFIDENCE = 0.75
JUMP_CENTER = 0.5       # centre moves more than half the box diagonal between neighbouring frames
JUMP_AREA = 2.0         # box area changes more than 2x between neighbouring frames
MAX_JUMP_GAP = 2        # only compare detections at most this many frames apart
UNSTABLE_RATE = 0.2     # jumps per second on screen; a dancer flinging an arm out is ~0.07
EDGE_PX = 2
EDGE_FLAG = 0.5         # flagged when clipped by the frame edge in more than half its frames
GAPPY_FLAG = 0.2        # flagged when missing from more than 20% of its own span
SPARSE_FILL = 0.15      # mask covers less than 15% of its box


@dataclass
class Track:
    clip: str
    track_id: str
    fps: float
    frame_size: tuple[int, int]  # (w, h)
    frames: np.ndarray           # (n,) sorted frame indices
    boxes: np.ndarray            # (n, 4) left, top, right, bottom (right/bottom exclusive)
    confidences: np.ndarray      # (n,)
    fill: dict[int, float] = field(default_factory=dict)  # frame -> mask area / box area, sampled
    label: str = ""              # what people see: "#3" for guests, "c7" for crowd

    @property
    def first(self) -> int:
        return int(self.frames[0])

    @property
    def last(self) -> int:
        return int(self.frames[-1])

    @property
    def seconds(self) -> float:
        """Time on screen (frames seen / fps), not the span."""
        return len(self.frames) / self.fps

    @property
    def confidence(self) -> float | None:
        c = self.confidences[~np.isnan(self.confidences)]
        return float(np.median(c)) if c.size else None

    def area_frac(self) -> np.ndarray:
        w, h = self.frame_size
        return (self.boxes[:, 2] - self.boxes[:, 0]) * (self.boxes[:, 3] - self.boxes[:, 1]) / (w * h)

    @property
    def median_area(self) -> float:
        return float(np.median(self.area_frac()))

    @property
    def kind(self) -> str:
        return "guest" if self.seconds >= MIN_GUEST_SECONDS and self.median_area >= MIN_GUEST_AREA else "crowd"

    def box_at(self, frame: int) -> tuple[int, int, int, int] | None:
        i = int(np.searchsorted(self.frames, frame))
        return tuple(int(v) for v in self.boxes[i]) if i < len(self.frames) and self.frames[i] == frame else None

    def presence(self, t0: float, t1: float) -> float:
        """Fraction of the frames in [t0, t1) seconds where this track is seen."""
        a = int(np.floor(t0 * self.fps))
        b = max(int(np.ceil(t1 * self.fps)), a + 1)
        return float(np.count_nonzero((self.frames >= a) & (self.frames < b)) / (b - a))

    def gaps(self) -> list[tuple[int, int]]:
        """Missing runs inside the track's span, as inclusive (first, last) frames."""
        d = np.diff(self.frames)
        return [(int(self.frames[i] + 1), int(self.frames[i + 1] - 1)) for i in np.nonzero(d > 1)[0]]

    @property
    def missing_frac(self) -> float:
        span = self.last - self.first + 1
        return 1 - len(self.frames) / span

    def jumps(self) -> list[int]:
        """Frames where the box leaps or changes size abruptly against the previous detection."""
        if len(self.frames) < 2:
            return []
        b = self.boxes.astype(float)
        cx, cy = (b[:, 0] + b[:, 2]) / 2, (b[:, 1] + b[:, 3]) / 2
        diag = np.hypot(b[:, 2] - b[:, 0], b[:, 3] - b[:, 1])
        area = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
        near = np.diff(self.frames) <= MAX_JUMP_GAP
        moved = np.hypot(np.diff(cx), np.diff(cy)) > JUMP_CENTER * diag[:-1]
        ratio = np.maximum(area[1:], 1) / np.maximum(area[:-1], 1)
        resized = (ratio > JUMP_AREA) | (ratio < 1 / JUMP_AREA)
        return [int(self.frames[i + 1]) for i in np.nonzero(near & (moved | resized))[0]]

    def edge_frac(self) -> float:
        w, h = self.frame_size
        b = self.boxes
        touch = (b[:, 0] <= EDGE_PX) | (b[:, 1] <= EDGE_PX) | (b[:, 2] >= w - EDGE_PX) | (b[:, 3] >= h - EDGE_PX)
        return float(touch.mean())

    @property
    def median_fill(self) -> float | None:
        return float(np.median(list(self.fill.values()))) if self.fill else None

    def flags(self) -> list[str]:
        out = []
        if self.seconds < MIN_GUEST_SECONDS:
            out.append("short")
        if self.median_area < MIN_GUEST_AREA:
            out.append("tiny")
        if self.confidence is not None and self.confidence < LOW_CONFIDENCE:
            out.append("low_confidence")
        if self.missing_frac > GAPPY_FLAG:
            out.append("gappy")
        if len(self.jumps()) / self.seconds > UNSTABLE_RATE:
            out.append("unstable")
        if self.edge_frac() > EDGE_FLAG:
            out.append("edge")
        if self.median_fill is not None and self.median_fill < SPARSE_FILL:
            out.append("sparse_mask")
        return out

    def summary(self) -> dict:
        return {
            "label": self.label, "track_id": self.track_id, "kind": self.kind,
            "first_s": round(self.first / self.fps, 2), "last_s": round((self.last + 1) / self.fps, 2),
            "seconds_on_screen": round(self.seconds, 2), "frames": len(self.frames),
            "median_area": round(self.median_area, 4), "confidence": round(self.confidence, 3) if self.confidence else None,
            "missing_frac": round(self.missing_frac, 3), "gaps": len(self.gaps()), "jumps": self.jumps(),
            "edge_frac": round(self.edge_frac(), 3),
            "median_fill": round(self.median_fill, 3) if self.median_fill is not None else None,
            "flags": self.flags(),
        }


def build_tracks(dets: list[sam.Detection], *, clip: str, fps: float, frame_size: tuple[int, int],
                 fills: dict[tuple[int, str], float] | None = None) -> list[Track]:
    """Group detections by id into Tracks, label them, and order guests (longest on screen first) before crowd."""
    by_id: dict[str, list[sam.Detection]] = {}
    for d in dets:
        by_id.setdefault(d.object_id, []).append(d)
    tracks = []
    for oid, ds in by_id.items():
        ds.sort(key=lambda d: d.frame)
        tracks.append(Track(
            clip=clip, track_id=oid, fps=fps, frame_size=frame_size,
            frames=np.array([d.frame for d in ds]),
            boxes=np.array([d.box for d in ds], dtype=int),
            confidences=np.array([d.confidence if d.confidence is not None else np.nan for d in ds], dtype=float),
            fill={f: v for (f, i), v in (fills or {}).items() if i == oid},
        ))
    assign_labels(tracks)
    tracks.sort(key=lambda t: (t.kind != "guest", -len(t.frames)))
    return tracks


def assign_labels(tracks: list[Track]) -> None:
    """Guests get #1, #2, ... and crowd c1, c2, ..., each in order of first appearance."""
    n = {"guest": 0, "crowd": 0}
    for t in sorted(tracks, key=lambda t: (t.first, int(t.track_id) if t.track_id.isdigit() else t.track_id)):
        n[t.kind] += 1
        t.label = f"#{n['guest']}" if t.kind == "guest" else f"c{n['crowd']}"


def fill_sample(dets: list[sam.Detection], every: int) -> list[sam.Detection]:
    """Every `every`-th detection of each id: enough to judge mask quality without decoding a whole clip."""
    seen: dict[str, int] = {}
    out = []
    for d in sorted(dets, key=lambda d: d.frame):
        k = seen.get(d.object_id, 0)
        if k % every == 0:
            out.append(d)
        seen[d.object_id] = k + 1
    return out
