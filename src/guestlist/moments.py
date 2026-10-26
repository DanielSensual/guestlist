"""Moments: Spark's events, checked against SAM's geometry before anyone trusts them.

Spark says "#2 is in a dip from 15 to 22 s". SAM knows on which frames #2 exists. Every claim
gets a mechanical status, so the review queue only shows a human the ones that don't add up.
"""

from __future__ import annotations

from .meta.spark import UNMARKED
from .tracks import Track

# A tag is supported when it is on screen for at least 1 s of the event (or half of a shorter event).
# Day-2 run: requiring half of every event marked background dancers "weak" in Spark's 6-8 s events
# although they were visibly there for 2-4 s of each.
MIN_ON_SCREEN_S = 1.0


def check_event(event: dict, tracks: dict[str, Track]) -> dict:
    """Per tag in the event: supported / weak / unsupported / unknown_tag / unmarked, plus an overall status."""
    t0, t1 = float(event["t_start"]), float(event["t_end"])
    need = min(MIN_ON_SCREEN_S, (t1 - t0) / 2)
    people = {}
    for tag in event.get("people", []):
        if tag == UNMARKED:
            people[tag] = {"status": "unmarked"}
            continue
        track = tracks.get(tag)
        if track is None:
            people[tag] = {"status": "unknown_tag"}
            continue
        on = track.presence(t0, t1) * max(t1 - t0, 0)
        people[tag] = {"status": "supported" if on >= need and on > 0 else "weak" if on > 0 else "unsupported",
                       "on_screen_s": round(on, 2)}
    statuses = {v["status"] for v in people.values()}
    if t1 <= t0:
        overall = "bad_time"
    elif statuses & {"unsupported", "unknown_tag"}:
        overall = "contradicted"
    elif "weak" in statuses or not people:
        overall = "review"
    else:
        overall = "supported"
    return {"t_start": t0, "t_end": t1, "people": people, "status": overall}


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
