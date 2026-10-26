#!/usr/bin/env python3
"""Day-2: windowed tracking, roster thumbnails and the marked-proxy experiment, on the 60 s dev proxy.

  1. SAM 3.1 concept pass in overlapping windows (one request stops at 16 ids), compared with the
     Day-1 single pass over the whole clip.
  2. Tracks with review signals; best-frame thumbnails and a contact sheet (renders/, local only).
  3. A marked proxy (outlines + #tags burned in) -> Muse Spark event log whose person labels are
     restricted to our tags -> every claim checked against SAM's frames.

Everything is cached, so re-running is free. Writes docs/day2-tracks.json.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from guestlist import burn, moments, proxy, thumbs, tracks, windows  # noqa: E402
from guestlist.meta import cache, files, sam, spark  # noqa: E402

RUN_CAP_USD = 3.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy", type=Path, default=ROOT / "proxies" / "spike60.mp4")
    ap.add_argument("--window", type=float, default=windows.WINDOW_S)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--keep-uploads", action="store_true")
    ap.add_argument("--no-spark", action="store_true")
    args = ap.parse_args()
    p = args.proxy
    start_spend = cache.spent()
    info = proxy.video_info(p)
    fps, frames = info["fps"], info["frames"]
    renders = ROOT / "renders" / "day2" / p.stem
    report: dict = {"date": time.strftime("%Y-%m-%d %H:%M %Z"), "proxy": {**info, "name": p.name}}

    # 1. windowed concept pass vs the single pass
    single = sam.segment_video(p, "person", max_usd=0.5)
    t = time.time()
    wr = windows.segment_windowed(p, "person", fps=fps, frames=frames, window_s=args.window,
                                  workers=args.workers, max_usd_per_call=0.5, keep_uploads=args.keep_uploads)
    report["windowed"] = {
        "window_s": args.window, "overlap_s": windows.OVERLAP_S, "wall_s": round(time.time() - t, 1),
        "requests": len(wr.windows) + len(wr.superseded), "frames_billed": wr.frames_billed, "usd": round(wr.usd, 4),
        "windows": [{"frames": [w.start, w.end], "ids": len(w.ids), "saturated": w.saturated,
                     "cached": w.result.cached, "seconds": w.result.meta.get("seconds")} for w in wr.windows],
        "split_because_full": [[w.start, w.end] for w in wr.superseded],
        "still_saturated": wr.saturated_spans(),
        "stitch_links": wr.links,
    }
    size = wr.frame_size or (info["width"], info["height"])
    fills = sam.mask_fills(tracks.fill_sample(wr.detections, every=6))
    trs = tracks.build_tracks(wr.detections, clip=p.stem, fps=fps, frame_size=size, fills=fills)
    single_trs = tracks.build_tracks(single.detections, clip=p.stem, fps=fps, frame_size=size)
    guests = [t for t in trs if t.kind == "guest"]
    late = 160  # Day 1: the single pass handed out its 16th id by frame ~73 and nothing new after frame 158

    def tally(ts: list[tracks.Track]) -> dict:
        return {"tracks": len(ts), "guests": sum(t.kind == "guest" for t in ts),
                "tracks_starting_after_frame_160": sum(t.first > late for t in ts),
                "longest_two_coverage": [round(len(t.frames) / frames, 3) for t in
                                         sorted(ts, key=lambda t: -len(t.frames))[:2]]}

    report["single_pass"] = {"frames_billed": single.frames_billed, "usd": round(single.usd, 4), **tally(single_trs)}
    report["windowed"].update(tally(trs))
    report["tracks"] = [t.summary() for t in trs]
    print(f"single pass: {report['single_pass']}")
    print(f"windowed:    {len(wr.windows)} windows (+{len(wr.superseded)} split), {wr.frames_billed} frames, "
          f"${wr.usd:.3f}; {tally(trs)}")

    # 2. thumbnails + contact sheet
    t = time.time()
    th = thumbs.best_thumbs(p, trs, thumbs.FaceFinder())
    by_key = {(d.frame, d.object_id): d for d in wr.detections}
    thumb_masks = sam.decode_masks([by_key[(x.frame, x.track_id)] for x in th.values()])
    thumbs.write_thumbs(th, renders / "thumbs")
    sheet = thumbs.contact_sheet(trs, th, renders.with_name(f"{p.stem}-contact.png"), title=p.stem, masks=thumb_masks)
    report["thumbs"] = {"seconds": round(time.time() - t, 1), "count": len(th),
                        "with_face": sum(x.face > 0 for x in th.values()),
                        "picked": {k: {"frame": x.frame, "face": x.face, "score": x.score} for k, x in th.items()}}
    print(f"thumbs: {len(th)} in {report['thumbs']['seconds']} s, {report['thumbs']['with_face']} with a face -> {sheet}")

    # 3. marked proxy -> Spark restricted to our tags -> checks
    if not args.no_spark and guests:
        t = time.time()
        guest_ids = {g.track_id for g in guests}
        masks = sam.decode_masks([d for d in wr.detections if d.object_id in guest_ids])
        marked = p.with_name(f"{p.stem}-marked.mp4")
        if not marked.exists():
            burn.burn_ids(p, guests, marked, masks=masks)
        proxy.frame_at(marked, frames // 2, fps, renders / "marked-mid.png")
        leg = burn.legend(guests)
        if cache.spent() - start_spend > RUN_CAP_USD:
            raise SystemExit(f"STOP: run cap ${RUN_CAP_USD} reached")
        log = spark.marked_event_log(marked, leg, max_usd=0.5)
        plain = spark.event_log(p)
        checks = moments.check_log(log.data, {g.label: g for g in guests})
        report["marked"] = {"render_s": round(time.time() - t, 1), "legend": leg, "usd": round(log.usd, 4),
                            "seconds": log.meta.get("seconds"), "cached": log.cached,
                            "usage": {k: log.usage.get(k) for k in ("input_tokens", "output_tokens")},
                            "log": log.data, "checks": checks}
        report["plain_log_for_comparison"] = {"people": plain.data.get("people"),
                                              "events": len(plain.data.get("events", []))}
        print(f"marked Spark log: ${log.usd:.4f}, {len(log.data.get('events', []))} events, "
              f"status {checks['event_status_counts']}, people {[x['label'] for x in log.data.get('people', [])]}")

        # control: a decoy tag in the legend that is drawn on nobody. Spark should never use it.
        decoy = f"#{len(guests) + 1}"
        dlog = spark.marked_event_log(marked, {**leg, decoy: "gold"}, max_usd=0.5)
        dchecks = moments.check_log(dlog.data, {g.label: g for g in guests})
        report["decoy_control"] = {
            "decoy": decoy, "usd": round(dlog.usd, 4),
            "in_people": decoy in {x["label"] for x in dlog.data.get("people", [])},
            "in_events": sum(decoy in e.get("people", []) for e in dlog.data.get("events", [])),
            "event_status_counts": dchecks["event_status_counts"],
            "first_seen_abs_error_s": dchecks["first_seen_abs_error_s"]}
        print(f"decoy control: {report['decoy_control']}")
        if not args.keep_uploads:
            files.delete(marked)

    report["spend"] = {"this_run_usd": round(cache.spent() - start_spend, 4), "ledger_total_usd": round(cache.spent(), 4)}
    (ROOT / "docs" / "day2-tracks.json").write_text(json.dumps(report, indent=2, default=str))
    print(f"\nthis run: ${cache.spent() - start_spend:.4f} · ledger total: ${cache.spent():.4f}")


if __name__ == "__main__":
    main()
