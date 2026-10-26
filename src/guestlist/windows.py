"""Windowed SAM 3.1 concept passes, stitched back into clip-wide tracks.

A concept pass hands out at most 16 object ids per request (Day-2 finding): on a crowded floor all
16 are taken within seconds and everyone who shows up later is never tracked. So a clip is cut into
short overlapping windows, any window that comes back with 16 ids is split and re-run, and the
windows are joined by box overlap on the frames they share. A window that is still full at the
minimum size is reported as saturated: people may be missing there, and the coverage ledger says so.
"""

from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .meta import cache, files, sam

WINDOW_S = 10.0
OVERLAP_S = 1.0
MIN_WINDOW_S = 5.0  # SAM bills 50 frames minimum (~4.2 s at 12 fps); smaller windows only add requests
STITCH_IOU = 0.5
STITCH_MIN_SHARED = 3  # one or two shared frames can't vouch for an irreversible join
STITCH_MARGIN = 0.1    # the best match must beat every rival for either side by this much


@dataclass
class Window:
    start: int  # first frame, global index
    end: int    # one past the last frame
    result: sam.SamResult

    @property
    def ids(self) -> set[str]:
        return {d.object_id for d in self.result.detections}

    @property
    def saturated(self) -> bool:
        return len(self.ids) >= sam.MAX_IDS


@dataclass
class WindowedResult:
    detections: list[sam.Detection]  # global frames, stitched ids "0", "1", ... by first appearance
    frame_size: tuple[int, int] | None
    windows: list[Window]
    links: list[dict] = field(default_factory=list)  # one per stitch across a seam
    superseded: list[Window] = field(default_factory=list)  # full windows that were split (still billed)

    @property
    def usd(self) -> float:
        """What the analysis cost when it ran (cached re-runs are free)."""
        return sum(w.result.usd for w in self.windows + self.superseded)

    @property
    def frames_billed(self) -> int:
        return sum(w.result.frames_billed for w in self.windows + self.superseded)

    def saturated_spans(self) -> list[tuple[int, int]]:
        return [(w.start, w.end) for w in self.windows if w.saturated]


def plan_windows(frames: int, fps: float, window_s: float = WINDOW_S, overlap_s: float = OVERLAP_S) -> list[tuple[int, int]]:
    """Overlapping [start, end) frame ranges covering the clip; a short tail is folded into the last window."""
    w, o = round(window_s * fps), round(overlap_s * fps)
    if not 0 <= o < w:
        raise ValueError(f"overlap ({o} frames) must be shorter than the window ({w} frames)")
    if frames <= w:
        return [(0, frames)]
    spans: list[tuple[int, int]] = []
    s = 0
    while s + w < frames:
        spans.append((s, s + w))
        s += w - o
    if frames - s < w // 2:
        spans[-1] = (spans[-1][0], frames)
    else:
        spans.append((s, frames))
    return spans


def split_span(start: int, end: int, overlap: int) -> list[tuple[int, int]]:
    mid = (start + end) // 2
    return [(start, min(end, mid + (overlap + 1) // 2)), (max(start, mid - overlap // 2), end)]


def cut_window(proxy: Path, start: int, end: int, fps: float, dst: Path) -> Path:
    """Frame-exact slice of the analysis proxy (no audio). Bit-exact, so a re-cut hits the SAM cache."""
    if dst.exists():
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".part.mp4")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(proxy),
                    "-vf", f"trim=start_frame={start}:end_frame={end},setpts=PTS-STARTPTS",
                    "-an", "-r", f"{fps:g}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-map_metadata", "-1",
                    "-fflags", "+bitexact", "-flags:v", "+bitexact", str(tmp)], check=True)
    tmp.rename(dst)
    return dst


def iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    iw = min(a[2], b[2]) - max(a[0], b[0])
    ih = min(a[3], b[3]) - max(a[1], b[1])
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def stitch(windows: list[Window], min_iou: float = STITCH_IOU) -> tuple[list[sam.Detection], list[dict]]:
    """Join per-window ids into clip-wide tracks: same person = high mean box IoU on the shared frames.

    A join needs enough shared frames and a clear winner; otherwise the seam is left open (recorded in `links`
    with made=False) and the two fragments go to the roster's merge proposals instead of being joined blind.
    """
    windows = sorted(windows, key=lambda w: w.start)
    parent: dict[tuple[int, str], tuple[int, str]] = {}

    def find(k):
        while parent.setdefault(k, k) != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    def boxes_by_id(wi: int, lo: int, hi: int) -> dict[str, dict[int, tuple]]:
        out: dict[str, dict[int, tuple]] = {}
        w = windows[wi]
        for d in w.result.detections:
            g = d.frame + w.start
            if lo <= g < hi:
                out.setdefault(d.object_id, {})[g] = d.box
        return out

    links: list[dict] = []
    for i in range(len(windows) - 1):
        a, b = windows[i], windows[i + 1]
        lo, hi = b.start, min(a.end, b.end)
        if hi <= lo:
            continue
        ba, bb = boxes_by_id(i, lo, hi), boxes_by_id(i + 1, lo, hi)
        scored = []
        for ia, fa in ba.items():
            for ib, fb in bb.items():
                shared = fa.keys() & fb.keys()
                if shared:
                    scored.append((float(np.mean([iou(fa[f], fb[f]) for f in shared])), len(shared), ia, ib))
        used_a, used_b = set(), set()
        for score, n, ia, ib in sorted(scored, reverse=True):
            if score < min_iou or ia in used_a or ib in used_b:
                continue
            rival = max((s_ for s_, _, xa, xb in scored if (xa == ia) != (xb == ib)), default=0.0)
            link = {"seam": [lo, hi], "from": f"w{i}:{ia}", "to": f"w{i + 1}:{ib}", "iou": round(score, 3),
                    "shared_frames": n, "rival_iou": round(rival, 3), "made": True}
            if n < STITCH_MIN_SHARED or score - rival < STITCH_MARGIN:
                link.update(made=False, reason="too few shared frames" if n < STITCH_MIN_SHARED else "ambiguous")
                links.append(link)
                continue
            used_a.add(ia)
            used_b.add(ib)
            parent[find((i + 1, ib))] = find((i, ia))
            links.append(link)

    seen: dict[tuple[int, str], int] = {}  # (global frame, root) already emitted
    first: dict[tuple[int, str], int] = {}
    raw: list[tuple[tuple[int, str], sam.Detection]] = []
    for wi, w in enumerate(windows):
        for d in w.result.detections:
            root = find((wi, d.object_id))
            g = d.frame + w.start
            if (g, root) in seen:  # the earlier window already covered this frame
                continue
            seen[(g, root)] = wi
            first[root] = min(first.get(root, g), g)
            raw.append((root, sam.Detection(g, "", d.box, d.confidence, d.mask)))
    order = {root: str(n) for n, root in enumerate(sorted(first, key=lambda r: (first[r], r)))}
    dets = []
    for root, d in raw:
        d.object_id = order[root]
        dets.append(d)
    dets.sort(key=lambda d: (d.frame, int(d.object_id)))
    return dets, links


def segment_windowed(proxy: str | Path, prompt: str = "person", *, fps: float, frames: int,
                     window_s: float = WINDOW_S, overlap_s: float = OVERLAP_S, min_window_s: float = MIN_WINDOW_S,
                     workers: int = 4, max_usd_per_call: float | None = None,
                     workdir: str | Path | None = None, keep_uploads: bool = False) -> WindowedResult:
    """SAM concept pass over a whole proxy in windows; full windows are split until they fit or hit the minimum."""
    proxy = Path(proxy)
    # window cuts are named by the proxy's content hash, so a replaced proxy never reuses stale cuts
    workdir = Path(workdir) if workdir else proxy.parent / "windows" / f"{proxy.stem}-{cache.sha256_file(proxy)[:8]}"
    overlap = round(overlap_s * fps)
    min_frames = round(min_window_s * fps)

    def run(span: tuple[int, int]) -> Window:
        s, e = span
        clip = cut_window(proxy, s, e, fps, workdir / f"{proxy.stem}_{s:06d}-{e:06d}.mp4")
        result = sam.segment_video(clip, prompt, max_usd=max_usd_per_call)
        if not keep_uploads and not result.cached:
            files.delete(clip)
        return Window(s, e, result)

    queue = plan_windows(frames, fps, window_s, overlap_s)
    done: list[Window] = []
    superseded: list[Window] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while queue:
            batch, queue = queue, []
            for w in pool.map(run, batch):
                if w.saturated and (w.end - w.start) // 2 >= min_frames:
                    superseded.append(w)
                    queue += split_span(w.start, w.end, overlap)
                else:
                    done.append(w)
    done.sort(key=lambda w: w.start)
    dets, links = stitch(done)
    size = next((w.result.frame_size for w in done if w.result.frame_size), None)
    return WindowedResult(dets, size, done, links, superseded)
