"""Moments: Spark's events, checked against SAM's geometry before anyone trusts them.

Spark says "#2 is in a dip from 15 to 22 s". SAM knows on which frames #2 exists. Every claim
gets a mechanical status, so the review queue only shows a human the ones that don't add up.

These are *presence* checks: they prove the tagged people were on screen when Spark says, not that
the action described is theirs or that the moment is any good ("presence_ok", never "verified").
"""

from __future__ import annotations

import math

from .meta.spark import UNMARKED
from .tracks import Track

# A co-star is present when on screen for at least 1 s of the event (or half of a shorter event).
# Day-2 run: requiring half of every event marked background dancers "weak" in Spark's 6-8 s events
# although they were visibly there for 2-4 s of each. The subject of a moment must cover half of it.
MIN_ON_SCREEN_S = 1.0
SUBJECT_COVERAGE = 0.5


def check_event(event: dict, tracks: dict[str, Track], *, subject: str | None = None,
                duration_s: float | None = None) -> dict:
    """Per tag: present / weak / absent / unknown_tag / unmarked; overall presence_ok / review / contradicted / bad_time."""
    t0, t1 = float(event["t_start"]), float(event["t_end"])
    if not (math.isfinite(t0) and math.isfinite(t1)) or t1 <= t0 or t0 < 0 or \
            (duration_s is not None and t1 > duration_s + 0.5):
        return {"t_start": t0, "t_end": t1, "people": {}, "status": "bad_time"}
    people = {}
    for tag in event.get("people", []):
        if tag == UNMARKED:
            people[tag] = {"status": "unmarked"}
            continue
        track = tracks.get(tag)
        if track is None:
            people[tag] = {"status": "unknown_tag"}
            continue
        p = track.presence(t0, t1)
        on = p * (t1 - t0)
        ok = p >= SUBJECT_COVERAGE if tag == subject else on >= min(MIN_ON_SCREEN_S, (t1 - t0) / 2)
        people[tag] = {"status": "present" if ok else "weak" if on > 0 else "absent", "on_screen_s": round(on, 2)}
    statuses = {v["status"] for v in people.values()}
    if statuses & {"absent", "unknown_tag"}:
        overall = "contradicted"
    elif "weak" in statuses or "present" not in statuses:  # nobody we track is provably there
        overall = "review"
    else:
        overall = "presence_ok"
    return {"t_start": t0, "t_end": t1, "people": people, "status": overall}


def check_person_moments(target: str, moments: list[dict], tracks: dict[str, Track], offset_s: float = 0.0,
                         duration_s: float | None = None) -> list[dict]:
    """A guest's moments (times relative to a sub-clip starting at `offset_s`) moved onto the clip's clock and
    checked: the guest must cover half of each moment, everyone they are `with` must be on screen in it."""
    out = []
    for m in moments:
        t0, t1 = m["t_start"] + offset_s, m["t_end"] + offset_s
        check = check_event({"t_start": t0, "t_end": t1, "people": [target, *m.get("with", [])]}, tracks,
                            subject=target, duration_s=duration_s)
        out.append({**m, "t_start": round(t0, 2), "t_end": round(t1, 2), "check": check})
    return out


def check_log(log: dict, tracks: dict[str, Track]) -> dict:
    """All events plus the people list (does the tag exist, and is it on screen when Spark says it first is)."""
    events = [check_event(e, tracks) for e in log.get("events", [])]
    people = []
    for p in log.get("people", []):
        tag, seen = p["label"], float(p.get("first_seen_s", 0))
        track = tracks.get(tag)
        row = {"label": tag, "first_seen_s": seen}
        if track is not None:
            row["track_first_s"] = round(track.first / track.fps, 2)
            row["first_seen_error_s"] = round(seen - track.first / track.fps, 2)
        people.append(row)
    counts: dict[str, int] = {}
    for e in events:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    errors = sorted(abs(p["first_seen_error_s"]) for p in people if "first_seen_error_s" in p)
    return {"events": events, "people": people, "event_status_counts": counts,
            "first_seen_abs_error_s": {"median": errors[len(errors) // 2] if errors else None,
                                       "within_1s": sum(e <= 1.0 for e in errors), "of": len(errors)},
            "tags_never_mentioned": sorted(set(tracks) - {p["label"] for p in log.get("people", [])})}
