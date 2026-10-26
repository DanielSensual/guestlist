"""Roster thumbnails: the best frame of every track, and a contact sheet per clip.

A human confirms the roster from these, so the frame should show the person large, central, sharp
and, when possible, facing the camera. Faces are only *detected* (YuNet, via GhostCut) to prefer
frames where one is visible; nothing here computes or stores a face embedding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .draw import color_for, draw_outline
from .tracks import EDGE_PX, Track

CANDIDATES = 6
MIN_SEPARATION_S = 1.0
PAD = 0.12
FACE_MIN_PX = 48       # crops narrower than this skip face detection
FACE_FULL_AREA = 0.02  # a face covering 2% of the crop gets full weight


@dataclass
class Thumb:
    label: str
    track_id: str
    frame: int
    box: tuple[int, int, int, int]
    score: float
    face: float
    sharpness: float
    image: np.ndarray = field(repr=False)          # padded crop from the proxy
    origin: tuple[int, int] = (0, 0)               # crop's top-left in frame pixels


def geometry_scores(track: Track) -> np.ndarray:
    """Per detection: big, central and not clipped by the frame edge."""
    w, h = track.frame_size
    b = track.boxes.astype(float)
    area = track.area_frac()
    size = np.sqrt(area / area.max())
    cx, cy = (b[:, 0] + b[:, 2]) / 2, (b[:, 1] + b[:, 3]) / 2
    centre = 1 - np.hypot((cx - w / 2) / (w / 2), (cy - h / 2) / (h / 2)) / np.sqrt(2)
    edge = (b[:, 0] <= EDGE_PX) | (b[:, 1] <= EDGE_PX) | (b[:, 2] >= w - EDGE_PX) | (b[:, 3] >= h - EDGE_PX)
    return size * (0.5 + 0.5 * centre) * np.where(edge, 0.6, 1.0)


def candidates(track: Track, k: int = CANDIDATES, min_sep_s: float = MIN_SEPARATION_S) -> list[int]:
    """The k best frames by geometry, at least `min_sep_s` apart so they are genuinely different looks."""
    scores = geometry_scores(track)
    sep = min_sep_s * track.fps
    picked: list[int] = []
    for i in np.argsort(-scores, kind="stable"):
        f = int(track.frames[i])
        if all(abs(f - p) >= sep for p in picked):
            picked.append(f)
            if len(picked) == k:
                break
    return picked


def read_frames(video: str | Path, wanted: set[int]) -> dict[int, np.ndarray]:
    """Decode only the frames we need, in one sequential pass."""
    out: dict[int, np.ndarray] = {}
    if not wanted:
        return out
    cap = cv2.VideoCapture(str(video))
    for i in range(max(wanted) + 1):
        if not cap.grab():
            break
        if i in wanted:
            ok, img = cap.retrieve()
            if ok:
                out[i] = img
    cap.release()
    return out


def crop(img: np.ndarray, box: tuple[int, int, int, int], pad: float = PAD) -> tuple[np.ndarray, tuple[int, int]]:
    h, w = img.shape[:2]
    l, t, r, b = box
    px, py = int((r - l) * pad), int((b - t) * pad)
    x0, y0 = max(0, l - px), max(0, t - py)
    return img[y0:min(h, b + py), x0:min(w, r + px)], (x0, y0)


def sharpness(img: np.ndarray) -> float:
    return float(cv2.Laplacian(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()) if img.size else 0.0


class FaceFinder:
    """YuNet face detection only (no recognition model is loaded)."""

    def __init__(self) -> None:
        from ghostcut.recap.faces import FaceEngine, ensure_models

        self._frontality = FaceEngine._frontality
        self._det = cv2.FaceDetectorYN.create(str(ensure_models()["yunet"]), "", (320, 320), 0.6)

    def score(self, img: np.ndarray) -> float:
        """0..1: a confident, frontal, reasonably large face in the top half of the crop."""
        h, w = img.shape[:2]
        if w < FACE_MIN_PX:
            return 0.0
        self._det.setInputSize((w, h))
        _, faces = self._det.detect(img)
        best = 0.0
        for row in faces if faces is not None else []:
            if row[1] + row[3] / 2 > h / 2:  # a face low in the crop belongs to someone else
                continue
            size = min(1.0, row[2] * row[3] / (w * h) / FACE_FULL_AREA)
            best = max(best, float(row[14]) * self._frontality(row) * size)
        return best


def best_thumbs(video: str | Path, tracks: list[Track], faces: FaceFinder | None = None) -> dict[str, Thumb]:
    """label -> the best frame for that track: geometry x relative sharpness x (1 + face)."""
    cands = {t.label: candidates(t) for t in tracks}
    imgs = read_frames(video, set().union(*cands.values()) if cands else set())
    out: dict[str, Thumb] = {}
    for t in tracks:
        geo = dict(zip(t.frames.tolist(), geometry_scores(t).tolist()))
        rows = []
        for f in cands[t.label]:
            if f not in imgs:
                continue
            box = t.box_at(f)
            c, origin = crop(imgs[f], box)
            rows.append((f, box, c, origin, sharpness(c), faces.score(c) if faces else 0.0))
        if not rows:
            continue
        top_sharp = max(r[4] for r in rows) or 1.0
        scored = [(geo[f] * (0.4 + 0.6 * s / top_sharp) * (1 + fa), f, box, c, origin, s, fa)
                  for f, box, c, origin, s, fa in rows]
        score, f, box, c, origin, s, fa = max(scored, key=lambda r: r[0])
        out[t.label] = Thumb(t.label, t.track_id, f, box, round(score, 4), round(fa, 3), round(s, 1), c, origin)
    return out


def write_thumbs(thumbs: dict[str, Thumb], outdir: str | Path) -> dict[str, Path]:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for label, th in thumbs.items():
        p = outdir / f"{label.replace('#', 'g')}.jpg"
        cv2.imwrite(str(p), th.image, [cv2.IMWRITE_JPEG_QUALITY, 90])
        paths[label] = p
    return paths


def _fmt(sec: float) -> str:
    return f"{int(sec // 60)}:{sec % 60:04.1f}"


def contact_sheet(tracks: list[Track], thumbs: dict[str, Thumb], out: str | Path, *, title: str = "",
                  masks: dict[tuple[int, str], np.ndarray] | None = None, cols: int = 6,
                  cell: tuple[int, int] = (240, 320)) -> Path:
    """Grid of thumbnails with the tracked person outlined and the track's numbers underneath."""
    cw, ch = cell
    strip, head = 62, 40
    items = [t for t in tracks if t.label in thumbs]
    rows = max(1, -(-len(items) // cols))
    sheet = np.full((head + rows * (ch + strip), cols * cw, 3), 24, np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    guests = sum(t.kind == "guest" for t in items)
    cv2.putText(sheet, f"{title}  {guests} guests, {len(items) - guests} crowd", (10, 27), font, 0.7,
                (235, 235, 235), 1, cv2.LINE_AA)
    for n, t in enumerate(items):
        th = thumbs[t.label]
        x, y = (n % cols) * cw, head + (n // cols) * (ch + strip)
        img = th.image.copy()
        s = min(cw / img.shape[1], ch / img.shape[0])
        img = cv2.resize(img, (max(1, int(img.shape[1] * s)), max(1, int(img.shape[0] * s))), interpolation=cv2.INTER_AREA)
        _, color = color_for(t.label)
        mask = (masks or {}).get((th.frame, t.track_id))
        draw_outline(img, th.box, mask, color, 2, offset=th.origin, scale=s)
        ox, oy = x + (cw - img.shape[1]) // 2, y + (ch - img.shape[0]) // 2
        sheet[oy:oy + img.shape[0], ox:ox + img.shape[1]] = img
        flags = ",".join(f for f in t.flags() if f not in ("short", "tiny")) or "-"
        conf = f"c{t.confidence:.2f}" if t.confidence is not None else ""
        lines = [(f"{t.label}  {_fmt(t.first / t.fps)}-{_fmt((t.last + 1) / t.fps)}", color),
                 (f"{t.seconds:.1f}s  {100 * t.median_area:.1f}%  {conf}  {t.kind}", (200, 200, 200)),
                 (flags, (120, 170, 255) if flags != "-" else (130, 130, 130))]
        for i, (text, c) in enumerate(lines):
            cv2.putText(sheet, text, (x + 6, y + ch + 18 + 19 * i), font, 0.47, c, 1, cv2.LINE_AA)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), sheet)
    return out
