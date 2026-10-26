"""Roster: tracks grouped into people. Every merge is proposed, checked, and confirmed by a human.

Two kinds of merge:
- within a clip: SAM drops an id when someone is hidden or leaves and comes back, so one person
  becomes several tracks. Candidates come from geometry: B starts soon after A ends, near where A
  was, at a similar size, and the two are (almost) never on screen together.
- across clips or cameras: there is no geometry to go on, only appearance.

Either way Muse Spark looks at a re-identification sheet (the query person in a few frames, the
candidates lettered underneath) and says which candidate, if any, is the same person, judging by
clothing, hair and build. It never names anyone, and only its answer is kept. Strong answers are
pre-selected as "suggested"; nothing merges until it is accepted.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np

from . import thumbs
from .tracks import MIN_GUEST_AREA, MIN_GUEST_SECONDS, Track

ELIGIBLE_SECONDS = 1.0  # shorter or smaller tracks stay crowd singletons: too little to compare
ELIGIBLE_AREA = 0.01
MAX_GAP_S = 5.0
MAX_COVISIBLE = 2       # frames two fragments of one person may share (SAM handing over an id)
LETTERS = "ABCDEFGH"    # candidates per sheet
# Day-3 known-answer eval on the club clips (29 split tracks, distractors provably other people), low effort:
#   conf >= 0.9: 9/29 found, 1 wrong person, 0/29 false matches when the person was absent
#   conf >= 0.8: 15/29 found, 2 wrong, 4/29 false     conf >= 0.7: 17/29 found, 5 wrong, 11/29 false
SUGGEST = 0.9           # pre-selected for one-click accept
REVIEW = 0.7            # shown to a human; below this Spark's pick is dropped
TILE = (150, 225)


def ref(t: Track) -> str:
    return f"{t.clip}/{t.track_id}"


def eligible(t: Track) -> bool:
    return t.seconds >= ELIGIBLE_SECONDS and t.median_area >= ELIGIBLE_AREA


def covisible(a: Track, b: Track) -> int:
    return int(np.intersect1d(a.frames, b.frames, assume_unique=True).size)


def _centre(box) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def _area(box) -> float:
    return max(1, (box[2] - box[0]) * (box[3] - box[1]))


def link_geometry(a: Track, b: Track) -> dict | None:
    """Could `b` be `a` continuing in the same clip? None when the geometry rules it out."""
    if b.clip != a.clip or b.first <= a.first:
        return None
    co = covisible(a, b)
    if co > MAX_COVISIBLE:
        return None
    gap = (b.first - a.last) / a.fps
    if gap > MAX_GAP_S:
        return None
    i = max(0, int(np.searchsorted(a.frames, b.first)) - 1)  # a's last box before b appears
    ea, sb = a.boxes[i], b.boxes[0]
    w, h = a.frame_size
    dist = math.dist(_centre(ea), _centre(sb)) / math.hypot(w, h)
    limit = 0.25 + 0.1 * max(gap, 0)
    ratio = _area(sb) / _area(ea)
    sim = min(ratio, 1 / ratio)
    if dist > limit or sim < 1 / 3:
        return None
    score = (1 - dist / limit) * (1 - max(gap, 0) / MAX_GAP_S) * sim
    return {"gap_s": round(float(gap), 2), "distance": round(float(dist), 3), "size_similarity": round(float(sim), 3),
            "covisible_frames": co, "score": round(float(score), 3)}


def within_candidates(tracks: list[Track]) -> dict[str, list[tuple[Track, dict]]]:
    """query ref -> up to 8 tracks that could continue it, best geometry first."""
    pool = [t for t in tracks if eligible(t)]
    out = {}
    for a in pool:
        cands = [(b, g) for b in pool if b is not a and (g := link_geometry(a, b))]
        if cands:
            out[ref(a)] = sorted(cands, key=lambda c: -c[1]["score"])[:len(LETTERS)]
    return out


def brighten(img: np.ndarray, mask: np.ndarray | None = None, target: float = 200.0, max_gain: float = 4.0) -> np.ndarray:
    """Lift a dark crop so the person's brightest 5% sit near `target` (club light is often 1-2 stops under)."""
    lum = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    vals = lum[mask > 0] if mask is not None and mask.any() else lum
    if not vals.size:
        return img
    gain = float(np.clip(target / max(float(np.percentile(vals, 95)), 1.0), 1.0, max_gain))
    return np.clip(img.astype(np.float32) * gain, 0, 255).astype(np.uint8) if gain > 1.01 else img


def isolate(img: np.ndarray, box: tuple[int, int, int, int], mask: np.ndarray | None) -> np.ndarray:
    """Padded crop with everything outside the person's mask dimmed and the mask outlined.

    Background people are often half hidden behind the dancers in front of them; without this a
    comparison sheet shows Spark the wrong person.
    """
    c, (x0, y0) = thumbs.crop(img, box)
    m = np.zeros(c.shape[:2], np.uint8)
    if mask is not None and mask.any():
        l, t = box[0] - x0, box[1] - y0
        sub = mask[:m.shape[0] - t, :m.shape[1] - l]
        m[t:t + sub.shape[0], l:l + sub.shape[1]] = sub
    lit = brighten(c, m)
    if not m.any():
        return lit
    out = (c * 0.3).astype(np.uint8)  # dim the *original* surroundings, or the gain would light them back up
    out[m > 0] = lit[m > 0]
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(out, contours, -1, (255, 255, 255), 1, cv2.LINE_AA)
    return out


def track_crops(video: str | Path, tracks: list[Track], dets: dict[tuple[int, str], "sam.Detection"],
                k: int = 3) -> dict[str, list[np.ndarray]]:
    """A few well-spread, isolated crops per track; frames decoded in one pass, masks in one batch."""
    from .meta import sam

    want = {ref(t): (t, thumbs.candidates(t, k=k, min_sep_s=0.5)) for t in tracks}
    imgs = thumbs.read_frames(video, {f for _, fs in want.values() for f in fs})
    src = {r: t.track_id.split(":")[0] for r, (t, _) in want.items()}  # split_track() ids look like "57:a"
    masks = sam.decode_masks([dets[(f, src[r])] for r, (t, fs) in want.items() for f in fs if (f, src[r]) in dets])
    return {r: [isolate(imgs[f], t.box_at(f), masks.get((f, src[r]))) for f in fs if f in imgs]
            for r, (t, fs) in want.items()}


def split_track(t: Track, gap_s: float = 1.0) -> tuple[Track, Track]:
    """Cut a track in two around its middle, dropping `gap_s` — a fragment pair whose answer we know."""
    mid = t.frames[len(t.frames) // 2]
    half = gap_s * t.fps / 2
    parts = []
    for name, keep in (("a", t.frames < mid - half), ("b", t.frames > mid + half)):
        parts.append(Track(t.clip, f"{t.track_id}:{name}", t.fps, t.frame_size, t.frames[keep], t.boxes[keep],
                           t.confidences[keep], label=f"{t.label}{name}"))
    return parts[0], parts[1]


def eval_cases(tracks: list[Track], min_seconds: float = 4.0, distractors: int = 5) -> list[tuple[Track, Track, list[Track]]]:
    """(first half, second half, distractors) per long track. Distractors are on screen together with the
    second half, so none of them can be the query person: the only right answer is the second half."""
    cases = []
    for t in tracks:
        if t.seconds < min_seconds or not eligible(t):
            continue
        a, b = split_track(t)
        others = [o for o in tracks if o is not t and eligible(o) and covisible(o, b) > b.fps]
        others.sort(key=lambda o: -covisible(o, b))
        if others:
            cases.append((a, b, others[:distractors]))
    return cases


def _tile(img: np.ndarray) -> np.ndarray:
    tw, th = TILE
    out = np.full((th, tw, 3), 32, np.uint8)
    if img is None or not img.size:
        return out
    s = min(tw / img.shape[1], th / img.shape[0])
    r = cv2.resize(img, (max(1, int(img.shape[1] * s)), max(1, int(img.shape[0] * s))), interpolation=cv2.INTER_AREA)
    y, x = (th - r.shape[0]) // 2, (tw - r.shape[1]) // 2
    out[y:y + r.shape[0], x:x + r.shape[1]] = r
    return out


def reid_sheet(query: list[np.ndarray], gallery: list[list[np.ndarray]], out: str | Path) -> Path:
    """QUERY row on top, then lettered candidates two per row, three frames each."""
    tw, th = TILE
    pad, head, k = 12, 40, 3
    block = k * tw + (k - 1) * 4
    width = 2 * block + 3 * pad
    rows = -(-len(gallery) // 2)
    sheet = np.full((pad + head + th + pad + rows * (head + th + pad), width, 3), 16, np.uint8)
    font = cv2.FONT_HERSHEY_DUPLEX

    def strip(crops, x, y):
        for i, c in enumerate(crops[:k]):
            sheet[y:y + th, x + i * (tw + 4):x + i * (tw + 4) + tw] = _tile(c)

    cv2.putText(sheet, "QUERY", (pad, pad + 30), font, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
    strip(query, pad, pad + head)
    for n, crops in enumerate(gallery):
        x = pad + (n % 2) * (block + pad)
        y = pad + head + th + pad + (n // 2) * (head + th + pad)
        cv2.rectangle(sheet, (x, y + 4), (x + 44, y + head - 2), (0, 200, 255), -1)
        cv2.putText(sheet, LETTERS[n], (x + 10, y + head - 9), font, 1.0, (0, 0, 0), 2, cv2.LINE_AA)
        strip(crops, x, y + head)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return out


@dataclass
class Proposal:
    a: str
    b: str
    scope: str                   # "within" | "across"
    geometry: dict | None = None
    spark: dict | None = None    # {"via": "match"|"also_same", "confidence", "evidence", "sheet"}
    status: str = "pending"      # suggested | pending | conflict | accepted | rejected
    decided_by: str = ""         # "human"; "rule" when another decision ruled it out; "script" in dev runs
    conflicts_with: list[str] = field(default_factory=list)  # proposals that can't also be true

    @property
    def id(self) -> str:
        return f"{self.a}~{self.b}"


def proposals_from_answer(query: str, letters: dict[str, str], answer: dict, scope: str,
                          geometry: dict[str, dict] | None = None, sheet: str = "") -> list[Proposal]:
    """Turn one Spark re-id answer into proposals. `letters` maps sheet letter -> candidate ref."""
    out = []
    picks = [("match", answer.get("match"))] + [("also_same", x) for x in answer.get("also_same", [])]
    seen = set()
    for via, letter in picks:
        if letter not in letters or letter in seen:
            continue
        seen.add(letter)
        cand = letters[letter]
        conf = float(answer.get("confidence", 0))
        if conf < REVIEW:
            continue
        out.append(Proposal(query, cand, scope, (geometry or {}).get(cand),
                            {"via": via, "confidence": round(conf, 3), "evidence": answer.get("evidence", ""),
                             "sheet": sheet},
                            "suggested" if via == "match" and conf >= SUGGEST else "pending"))
    return out


def flag_conflicts(proposals: list[Proposal], covisible_pairs: set[frozenset]) -> None:
    """Two people seen together can't both be the same third person: such suggestions go to a human."""
    by_target: dict[str, list[Proposal]] = {}
    for p in proposals:
        if p.scope == "across" and p.status in ("suggested", "pending"):
            by_target.setdefault(p.b, []).append(p)
    for ps in by_target.values():
        for i, p in enumerate(ps):
            for q in ps[i + 1:]:
                if frozenset((p.a, q.a)) in covisible_pairs:
                    p.status = q.status = "conflict"
                    p.conflicts_with.append(q.id)
                    q.conflicts_with.append(p.id)


class Roster:
    """roster.json: tracks (summaries + thumbnails), proposals, names. People are derived, never stored."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        data = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.clips: dict = data.get("clips", {})
        self.tracks: dict[str, dict] = data.get("tracks", {})
        self.proposals: list[Proposal] = [Proposal(**p) for p in data.get("proposals", [])]
        self.names: dict[str, str] = data.get("names", {})
        # each confirmation is the exact set of tracks the human saw; a later merge un-confirms the person
        self.confirmed: list[list[str]] = [[c] if isinstance(c, str) else sorted(c) for c in data.get("confirmed", [])]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"clips": self.clips, "tracks": self.tracks,
                                   "proposals": [asdict(p) for p in self.proposals],
                                   "names": self.names, "confirmed": self.confirmed}, indent=1))
        tmp.replace(self.path)

    def proposal(self, pid: str) -> Proposal:
        return next(p for p in self.proposals if p.id == pid)

    def decide(self, pid: str, accept: bool, by: str = "human") -> None:
        """Record a decision. Accepting one side of a conflict rejects the other: those two people were seen
        together. Accepting a proposal whose rival is already accepted is refused."""
        p = self.proposal(pid)
        rivals = [q for q in self.proposals if q.id in p.conflicts_with]
        if accept and any(q.status == "accepted" for q in rivals):
            raise ValueError(f"{p.a} = {p.b} is ruled out: a person seen together with {p.a} was already "
                             f"confirmed as {p.b}")
        p.status, p.decided_by = ("accepted" if accept else "rejected"), by
        if accept:
            for q in rivals:
                if q.status not in ("accepted", "rejected"):
                    q.status, q.decided_by = "rejected", "rule"

    def accept_suggested(self, by: str = "human") -> int:
        """Accept every suggestion through `decide`, so conflict rules apply to bulk accepts too."""
        n = 0
        for p in self.proposals:
            if p.status == "suggested":
                self.decide(p.id, True, by)
                n += 1
        return n

    def add(self, proposals: list[Proposal]) -> None:
        """Add new proposals; a pair already decided keeps its decision."""
        have = {p.id: p for p in self.proposals}
        for p in proposals:
            old = have.get(p.id)
            if old is None:
                self.proposals.append(p)
            elif old.status not in ("accepted", "rejected"):
                self.proposals[self.proposals.index(old)] = p

    def _order(self, r: str) -> tuple:
        t = self.tracks[r]
        return (list(self.clips).index(t["clip"]) if t["clip"] in self.clips else 0, t["first_s"], r)

    def people(self) -> list[dict]:
        """Union of accepted merges -> people, labelled #1.. (guests) and c1.. (crowd) by first appearance."""
        parent = {r: r for r in self.tracks}

        def find(r):
            while parent[r] != r:
                parent[r] = parent[parent[r]]
                r = parent[r]
            return r

        for p in self.proposals:
            if p.status == "accepted" and p.a in parent and p.b in parent:
                ra, rb = find(p.a), find(p.b)
                if ra != rb:
                    first, second = sorted((ra, rb), key=self._order)
                    parent[second] = first
        groups: dict[str, list[str]] = {}
        for r in self.tracks:
            groups.setdefault(find(r), []).append(r)
        people = []
        for anchor, refs in groups.items():
            refs.sort(key=self._order)
            ts = [self.tracks[r] for r in refs]
            seconds = sum(t["seconds_on_screen"] for t in ts)
            area = sum(t["median_area"] * t["seconds_on_screen"] for t in ts) / seconds if seconds else 0.0
            name = next((self.names[r] for r in refs if self.names.get(r)), "")
            people.append({
                "id": refs[0], "tracks": refs, "clips": sorted({t["clip"] for t in ts}, key=list(self.clips).index),
                "seconds": round(seconds, 2), "area": round(area, 4), "name": name,
                "kind": "guest" if seconds >= MIN_GUEST_SECONDS and area >= MIN_GUEST_AREA else "crowd",
                "confirmed": sorted(refs) in self.confirmed,
                "thumb": max(ts, key=lambda t: t["seconds_on_screen"]).get("thumb"),
            })
        people.sort(key=lambda p: self._order(p["id"]))
        n = {"guest": 0, "crowd": 0}
        for p in people:
            n[p["kind"]] += 1
            p["label"] = f"#{n['guest']}" if p["kind"] == "guest" else f"c{n['crowd']}"
        return people

    def person(self, pid: str) -> dict:
        return next(p for p in self.people() if p["id"] == pid or pid in p["tracks"])

    def set_name(self, pid: str, name: str) -> None:
        self.names[self.person(pid)["id"]] = name.strip()

    def confirm(self, pid: str) -> None:
        members = sorted(self.person(pid)["tracks"])
        if members not in self.confirmed:
            self.confirmed.append(members)
