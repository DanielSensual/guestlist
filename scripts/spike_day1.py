#!/usr/bin/env python3
"""Day-1 API spike: measure what the Guestlist budget depends on, on one 60 s dev proxy.

  SAM 3.1 concept pass ("person"), one box-prompt re-track (forward from mid-clip),
  Muse Spark 1.3 video event log (structured JSON), token counts at 20 s and 60 s,
  Muse Voice Transcribe diarization.

Everything is cached, so re-running is free. Writes docs/spike-day1.json and a
local overlay PNG under renders/ (gitignored: the dev clip is not demo footage).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from guestlist import proxy  # noqa: E402
from guestlist.meta import cache, files, pricing, sam, spark, transcribe  # noqa: E402

DEV_CLIP = ROOT / ".cache" / "dev-clip.mp4"  # private dev footage, never in the repo: symlink it here or pass --clip
RUN_CAP_USD = 10.0
CALL_CAP_USD = 2.0


def spent_this_run(start: float) -> float:
    return cache.spent() - start


def check(start: float, estimate: float, what: str) -> None:
    if estimate > CALL_CAP_USD:
        raise SystemExit(f"STOP: {what} estimated ${estimate:.2f} > per-call cap ${CALL_CAP_USD:.2f}")
    if spent_this_run(start) + estimate > RUN_CAP_USD:
        raise SystemExit(f"STOP: {what} would push this run past ${RUN_CAP_USD:.2f}")


def overlay(png_in: Path, dets: list[sam.Detection], png_out: Path) -> None:
    img = cv2.imread(str(png_in))
    colors = [(66, 135, 245), (245, 182, 66), (80, 200, 120), (200, 80, 200)]
    for i, d in enumerate(dets):
        c = colors[i % len(colors)]
        l, t, r, b = d.box
        m = d.mask_array()
        if m is not None:
            region = img[t:t + m.shape[0], l:l + m.shape[1]]
            sel = m[:region.shape[0], :region.shape[1]].astype(bool)
            region[sel] = (0.55 * region[sel] + 0.45 * np.array(c)).astype(np.uint8)
        cv2.rectangle(img, (l, t), (r - 1, b - 1), c, 2)
        cv2.putText(img, f"id {d.object_id} c={d.confidence:.2f}" if d.confidence is not None else f"id {d.object_id}",
                    (l + 4, max(18, t + 18)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, c, 2)
    png_out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(png_out), img)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", type=Path, default=DEV_CLIP)
    ap.add_argument("--start", type=float, default=30.0)
    ap.add_argument("--keep-uploads", action="store_true")
    ap.add_argument("--skip-transcribe", action="store_true")
    args = ap.parse_args()

    start_spend = cache.spent()
    report: dict = {"date": time.strftime("%Y-%m-%d %H:%M %Z"), "source": args.clip.name,
                    "source_info": proxy.video_info(args.clip)}

    # 1. proxies (720 short side, 12 fps CFR, faststart) — the only thing uploaded
    pdir = ROOT / "proxies"
    p60 = pdir / "spike60.mp4"
    p20 = pdir / "spike20.mp4"
    if not p60.exists():
        proxy.make_proxy(args.clip, p60, start=args.start, duration=60)
    if not p20.exists():
        proxy.make_proxy(args.clip, p20, start=args.start, duration=20)
    info = proxy.video_info(p60)
    report["proxy"] = {**info, "bytes": p60.stat().st_size, "proxy20_bytes": p20.stat().st_size}
    print(f"proxy: {info['width']}x{info['height']} {info['fps']:.0f} fps {info['frames']} frames "
          f"{p60.stat().st_size / 1e6:.1f} MB")

    # 2. token counts (no generation): text-only baseline, 20 s and 60 s video
    counts = {}
    try:
        counts["text_only"] = spark.count_text_tokens()
        counts["video_20s"] = spark.count_video_tokens(p20)
        counts["video_60s"] = spark.count_video_tokens(p60)
        per_sec = (counts["video_60s"] - counts["video_20s"]) / 40
        counts["tokens_per_video_second"] = round(per_sec, 1)
        counts["fixed_overhead_tokens"] = round(counts["video_60s"] - 60 * per_sec)
        print(f"tokens: text {counts['text_only']}, 20s {counts['video_20s']}, 60s {counts['video_60s']} "
              f"-> {per_sec:.1f} tok/s")
    except Exception as e:  # report and fall back to Spark usage below
        counts["error"] = f"{type(e).__name__}: {e}"
        print("token count endpoint failed:", counts["error"])
    report["token_counts"] = counts

    # 3. SAM concept pass
    est = pricing.sam_video_cost(info["frames"])
    check(start_spend, est, "SAM concept pass")
    t = time.time()
    concept = sam.segment_video(p60, "person")
    tracks = concept.tracks()
    confs = [d.confidence for d in concept.detections if d.confidence is not None]
    report["sam_concept"] = {
        "prompt": "person", "cached": concept.cached, "frames_billed": concept.frames_billed,
        "usd": round(concept.usd, 4), "seconds": concept.meta.get("seconds"),
        "first_frame_seconds": concept.meta.get("first_frame_seconds"), "frame_size": concept.frame_size,
        "frames_with_detections": len({d.frame for d in concept.detections}),
        "objects": {oid: {"frames": len(ds), "first": ds[0].frame, "last": ds[-1].frame,
                          "mean_conf": round(statistics.mean([d.confidence for d in ds if d.confidence is not None] or [0]), 3)}
                    for oid, ds in tracks.items()},
        "conf_min": round(min(confs), 3) if confs else None, "conf_mean": round(statistics.mean(confs), 3) if confs else None,
        "text_bytes": len(concept.text),
    }
    print(f"SAM concept: {len(tracks)} objects, {concept.frames_billed} frames billed, ${concept.usd:.3f}, "
          f"{concept.meta.get('seconds')} s (cached={concept.cached})")

    # mask decode check + overlay on the mid frame
    mid = info["frames"] // 2
    mid_dets = [d for d in concept.detections if d.frame == mid] or \
               [d for d in concept.detections if d.frame == min({d.frame for d in concept.detections},
                                                                key=lambda f: abs(f - mid))]
    mid = mid_dets[0].frame if mid_dets else mid
    decoded = []
    for d in mid_dets:
        m = d.mask_array()
        decoded.append({"id": d.object_id, "box": d.box, "mask_hw": list(m.shape) if m is not None else None,
                        "mask_fill": round(float(m.mean()), 3) if m is not None else None,
                        "box_hw": [d.box[3] - d.box[1], d.box[2] - d.box[0]]})
    report["mask_check"] = {"frame": mid, "decoded": decoded}
    png = proxy.frame_at(p60, mid, info["fps"], ROOT / "renders" / "spike-mid.png")
    overlay(png, mid_dets, ROOT / "renders" / "spike-mid-overlay.png")

    # 4. box-prompt re-track of the largest person, forward from the mid frame
    if mid_dets:
        target = max(mid_dets, key=lambda d: (d.box[2] - d.box[0]) * (d.box[3] - d.box[1]))
        size = concept.frame_size or (info["width"], info["height"])
        prompt = sam.build_objects_prompt(size, {1: (mid, target.box)})
        est = pricing.sam_video_cost(info["frames"] - mid)
        check(start_spend, est, "SAM box re-track")
        retrack = sam.segment_video(p60, prompt, direction="forward")
        rt = retrack.tracks().get("1", [])
        report["sam_box_retrack"] = {
            "prompt": prompt, "from_frame": mid, "cached": retrack.cached,
            "frames_billed": retrack.frames_billed, "usd": round(retrack.usd, 4),
            "seconds": retrack.meta.get("seconds"), "frames_tracked": len(rt),
            "first": rt[0].frame if rt else None, "last": rt[-1].frame if rt else None,
            "mean_conf": round(statistics.mean([d.confidence for d in rt if d.confidence is not None] or [0]), 3),
            "mask_encoding_seen": sorted({str(d.mask.encoding) for d in rt if d.mask is not None}),
        }
        print(f"SAM box re-track: {len(rt)} frames tracked, {retrack.frames_billed} billed, ${retrack.usd:.3f}")

    # 5. Spark event log
    tok = counts.get("video_60s") or 60 * 300
    est = pricing.token_cost("muse-spark-1.3", tok + 600, 0, 16000)
    check(start_spend, est, "Spark event log")
    log = spark.event_log(p60)
    tin, tcached, tout, treason = spark._usage_numbers(log.usage)
    report["spark_event_log"] = {
        "cached": log.cached, "usd": round(log.usd, 4), "seconds": log.meta.get("seconds"),
        "input_tokens": tin, "cached_tokens": tcached, "output_tokens": tout, "reasoning_tokens": treason,
        "status": log.meta.get("status"), "people": len(log.data.get("people", [])),
        "events": len(log.data.get("events", [])),
        "rate_limit_headers": {k: v for k, v in (log.meta.get("headers") or {}).items() if "ratelimit" in k.lower()},
    }
    print(f"Spark: {tin} in / {tout} out ({treason} reasoning), ${log.usd:.4f}, {log.meta.get('seconds')} s, "
          f"{len(log.data.get('people', []))} people, {len(log.data.get('events', []))} events")

    # 6. Voice Transcribe diarization
    if not args.skip_transcribe:
        wav = proxy.extract_wav(p60, pdir / "spike60.wav")
        try:
            tr = transcribe.diarize(wav)
            report["transcribe"] = {"turns": len(tr.get("turns", [])),
                                    "speakers": sorted({t.get("speaker") for t in tr.get("turns", []) if t.get("speaker")}),
                                    "audio_ms": tr.get("audioDurationMs"),
                                    "transcript_chars": len(tr.get("transcript", ""))}
            print(f"transcribe: {report['transcribe']}")
        except Exception as e:
            report["transcribe"] = {"error": f"{type(e).__name__}: {e}"}
            print("transcribe failed:", report["transcribe"]["error"])

    # 7. totals + projection for the demo set (2 cams x 20 min at 12 fps)
    run_usd = spent_this_run(start_spend)
    tps = counts.get("tokens_per_video_second") or (tin / 60)
    demo_seconds = 2 * 20 * 60
    report["spend"] = {"this_run_usd": round(run_usd, 4), "ledger_total_usd": round(cache.spent(), 4)}
    report["projection_demo_set"] = {
        "assumption": "2 cameras x 20 min, 12 fps proxies, one SAM concept pass + 25% box re-tracks, "
                      "one Spark log per clip (output ~ this run's ratio)",
        "sam_usd": round(pricing.sam_video_cost(demo_seconds * 12) * 1.25, 2),
        "spark_usd": round(pricing.token_cost("muse-spark-1.3", int(tps * demo_seconds), 0,
                                              int(tout * demo_seconds / 60)), 2),
    }
    report["projection_demo_set"]["total_usd"] = round(sum(v for k, v in report["projection_demo_set"].items()
                                                           if k.endswith("_usd")), 2)
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "spike-day1.json").write_text(json.dumps(report, indent=2, default=str))
    print(f"\nthis run: ${run_usd:.4f} · ledger total: ${cache.spent():.4f}")
    print("projection (demo set):", report["projection_demo_set"])

    if not args.keep_uploads:
        for p in (p60, p20):
            try:
                files.delete(p)
            except Exception as e:
                print("delete failed:", p.name, e)


if __name__ == "__main__":
    main()
