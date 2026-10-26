#!/usr/bin/env python3
"""Day-3: the roster, on two dev clips (the 60 s Day-1 clip + a later minute of the same night).

  prepare  windowed SAM + tracks + thumbnails for every clip
  eval     how far Spark's "same person?" answers can be trusted: known-answer sheets built by cutting
           long tracks in two, with distractors that are provably other people (on screen at the same time)
  within   fragment-merge proposals inside each clip (geometry candidates -> Spark picks)
  across   person-level proposals between the clips (appearance only) + conflict check
  moments  per-person moments on a marked proxy re-tagged with roster labels, checked against SAM

Everything is cached. Writes projects/dev/roster.json (local: it holds crops) and docs/day3-roster.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cv2  # noqa: E402

from guestlist import burn, moments, proxy, roster, thumbs, tracks, windows  # noqa: E402
from guestlist.meta import cache, files, sam, spark  # noqa: E402

PROJECT = ROOT / "projects" / "dev"
DEV_CLIP = ROOT / ".cache" / "dev-clip.mp4"
CLIPS = {"spike60": 30.0, "later60": 120.0}  # name -> start second in the dev clip
RUN_CAP_USD = 4.0


def load_clip(name: str, start: float) -> dict:
    p = ROOT / "proxies" / f"{name}.mp4"
    if not p.exists():
        proxy.make_proxy(DEV_CLIP, p, start=start, duration=60)
    info = proxy.video_info(p)
    wr = windows.segment_windowed(p, "person", fps=info["fps"], frames=info["frames"], max_usd_per_call=0.5)
    size = wr.frame_size or (info["width"], info["height"])
    fills = sam.mask_fills(tracks.fill_sample(wr.detections, every=6))
    trs = tracks.build_tracks(wr.detections, clip=name, fps=info["fps"], frame_size=size, fills=fills)
    return {"name": name, "proxy": p, "info": info, "windowed": wr, "tracks": trs,
            "dets": {(d.frame, d.object_id): d for d in wr.detections}}


def stable_index(key: str, n: int) -> int:
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % n


def run_eval(clips: list[dict], efforts: list[str], workers: int) -> dict:
    jobs = []
    for c in clips:
        for a, b, others in roster.eval_cases(c["tracks"]):
            crops = roster.track_crops(c["proxy"], [a, b, *others], c["dets"])
            for with_truth in (True, False):
                gallery = list(others)
                truth_letter = None
                if with_truth:
                    i = stable_index(roster.ref(a), len(others) + 1)
                    gallery.insert(i, b)
                    truth_letter = roster.LETTERS[i]
                tag = f"{c['name']}-{a.track_id.replace(':', '')}-{'t' if with_truth else 'n'}"
                sheet = roster.reid_sheet(crops[roster.ref(a)], [crops[roster.ref(g)] for g in gallery],
                                          PROJECT / "eval" / f"{tag}.jpg")
                jobs.append((tag, sheet, roster.LETTERS[:len(gallery)], truth_letter, a.label))
    out: dict = {"cases": len(jobs) // 2, "by_effort": {}}

    def ask(job, effort):
        tag, sheet, letters, truth, label = job
        try:
            r = spark.same_person(sheet, list(letters), 3, effort=effort, max_usd=0.2)
        except spark.SparkNoAnswer as e:  # counts as "no match": the safe failure
            return {"tag": tag, "truth": truth or spark.NONE, "match": spark.NONE, "also_same": [],
                    "confidence": 0.0, "usd": 0.0, "evidence": f"no answer: {e}"}
        return {"tag": tag, "truth": truth or spark.NONE, "match": r.data["match"],
                "also_same": r.data["also_same"], "confidence": r.data["confidence"], "usd": r.usd,
                "evidence": r.data["evidence"]}

    for effort in efforts:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(lambda j: ask(j, effort), jobs))
        pos = [r for r in rows if r["truth"] != spark.NONE]
        neg = [r for r in rows if r["truth"] == spark.NONE]

        def at(th):
            hit = sum(r["match"] == r["truth"] and r["confidence"] >= th for r in pos)
            wrong_pos = sum(r["match"] not in (r["truth"], spark.NONE) and r["confidence"] >= th for r in pos)
            false_neg = sum(r["match"] != spark.NONE and r["confidence"] >= th for r in neg)
            return {"threshold": th, "found": hit, "of_positives": len(pos), "wrong_person_on_positives": wrong_pos,
                    "false_match_on_negatives": false_neg, "of_negatives": len(neg)}

        out["by_effort"][effort] = {"usd": round(sum(r["usd"] for r in rows), 4),
                                    "at": [at(th) for th in (0.0, 0.5, 0.7, 0.8, 0.9)], "rows": rows}
        print(f"eval {effort}: " + " | ".join(
            f"≥{a['threshold']}: {a['found']}/{a['of_positives']} found, {a['wrong_person_on_positives']} wrong, "
            f"{a['false_match_on_negatives']}/{a['of_negatives']} false" for a in out["by_effort"][effort]["at"]))
    return out


def ask_sheet(sheet: Path, letters: list[str]) -> dict | None:
    try:
        return spark.same_person(sheet, letters, 3, effort="low", max_usd=0.2).data
    except spark.SparkNoAnswer:
        return None


def fill_roster(R: roster.Roster, clips: list[dict]) -> None:
    """Every track of every clip into roster.json, each with an isolated best-frame thumbnail."""
    for c in clips:
        R.clips[c["name"]] = {"proxy": str(c["proxy"].relative_to(ROOT)), **c["info"]}
        th = thumbs.best_thumbs(c["proxy"], c["tracks"])
        masks = sam.decode_masks([c["dets"][(x.frame, x.track_id)] for x in th.values()])
        imgs = thumbs.read_frames(c["proxy"], {x.frame for x in th.values()})
        by_id = {t.track_id: t for t in c["tracks"]}
        for x in th.values():
            rel = Path("thumbs") / c["name"] / f"{x.track_id}.jpg"
            (PROJECT / rel).parent.mkdir(parents=True, exist_ok=True)
            crop = roster.isolate(imgs[x.frame], x.box, masks.get((x.frame, x.track_id)))
            cv2.imwrite(str(PROJECT / rel), crop, [cv2.IMWRITE_JPEG_QUALITY, 88])
            t = by_id[x.track_id]
            R.tracks[roster.ref(t)] = {**t.summary(), "clip": c["name"], "thumb": str(rel)}


def run_within(R: roster.Roster, clips: list[dict], workers: int) -> dict:
    jobs = []
    for c in clips:
        cands = roster.within_candidates(c["tracks"])
        by = {roster.ref(t): t for t in c["tracks"]}
        need = set(cands) | {roster.ref(b) for cl in cands.values() for b, _ in cl}
        crops = roster.track_crops(c["proxy"], [by[r] for r in need], c["dets"])
        for q, cl in cands.items():
            letters = {roster.LETTERS[i]: roster.ref(b) for i, (b, _) in enumerate(cl)}
            sheet = roster.reid_sheet(crops[q], [crops[roster.ref(b)] for b, _ in cl],
                                      PROJECT / "reid" / f"{q.replace('/', '-')}.jpg")
            jobs.append((q, letters, {roster.ref(b): g for b, g in cl}, sheet))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        answers = list(pool.map(lambda j: ask_sheet(j[3], list(j[1])), jobs))
    props = []
    for (q, letters, geo, sheet), ans in zip(jobs, answers):
        if ans:
            props += roster.proposals_from_answer(q, letters, ans, "within", geo, str(sheet.relative_to(PROJECT)))
    R.add(props)
    counts = {s: sum(p.status == s for p in props) for s in ("suggested", "pending")}
    out = {"queries": len(jobs), "no_answer": answers.count(None),
           "spark_said_none": sum(1 for a in answers if a and a["match"] == spark.NONE), **counts}
    print(f"within: {out}")
    return out


def person_tracks(c: dict, people: list[dict]) -> tuple[dict[str, tracks.Track], list]:
    """One Track per person in this clip (their fragments joined), keyed and labelled by roster label.
    Also returns the relabelled detections (id = index into `people`), for mask decoding."""
    idx = {r: str(i) for i, p in enumerate(people) for r in p["tracks"]}
    dets, seen = [], set()
    for d in c["windowed"].detections:
        pid = idx.get(f"{c['name']}/{d.object_id}")
        if pid is not None and (d.frame, pid) not in seen:  # fragments may share a frame or two at a hand-over
            seen.add((d.frame, pid))
            dets.append(sam_detection(d, pid))
    out = {}
    for t in tracks.build_tracks(dets, clip=c["name"], fps=c["info"]["fps"], frame_size=c["tracks"][0].frame_size):
        t.label = people[int(t.track_id)]["label"]
        out[t.label] = t
    return out, dets


def sam_detection(d, new_id: str):
    return sam.Detection(d.frame, new_id, d.box, d.confidence, d.mask)


def run_across(R: roster.Roster, clips: list[dict], workers: int, min_seconds: float = 3.0) -> dict:
    """Guest people of each clip against the other clip's guests, 8 per sheet; best answer per query wins."""
    people = R.people()
    in_clip = {c["name"]: [p for p in people if p["kind"] == "guest" and p["clips"] == [c["name"]]
                           and p["seconds"] >= min_seconds] for c in clips}
    by_name = {c["name"]: c for c in clips}
    lead = {p["id"]: max(p["tracks"], key=lambda r: R.tracks[r]["seconds_on_screen"]) for ps in in_clip.values() for p in ps}
    crops = {}
    for name, ps in in_clip.items():
        c = by_name[name]
        by = {roster.ref(t): t for t in c["tracks"]}
        crops.update(roster.track_crops(c["proxy"], [by[lead[p["id"]]] for p in ps], c["dets"]))
    a_name, b_name = clips[0]["name"], clips[1]["name"]
    jobs = []
    for p in in_clip[a_name]:
        gallery = in_clip[b_name]
        for page in range(0, len(gallery), len(roster.LETTERS)):
            g = gallery[page:page + len(roster.LETTERS)]
            letters = {roster.LETTERS[i]: lead[x["id"]] for i, x in enumerate(g)}
            sheet = roster.reid_sheet(crops[lead[p["id"]]], [crops[lead[x["id"]]] for x in g],
                                      PROJECT / "reid" / f"across-{lead[p['id']].replace('/', '-')}-p{page}.jpg")
            jobs.append((lead[p["id"]], letters, sheet))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        answers = list(pool.map(lambda j: ask_sheet(j[2], list(j[1])), jobs))
    best: dict[str, list] = {}
    for (q, letters, sheet), ans in zip(jobs, answers):
        if ans and ans["match"] != spark.NONE:
            if q not in best or ans["confidence"] > best[q][1]["confidence"]:
                best[q] = (letters, ans, sheet)
    props = []
    for q, (letters, ans, sheet) in best.items():
        props += roster.proposals_from_answer(q, letters, {**ans, "also_same": []}, "across",
                                              sheet=str(sheet.relative_to(PROJECT)))
    # people seen together in clip A can't both be one person from clip B
    a_tracks = {roster.ref(t): t for t in by_name[a_name]["tracks"]}
    together = set()
    ps = in_clip[a_name]
    for i, p in enumerate(ps):
        for q in ps[i + 1:]:
            if any(roster.covisible(a_tracks[x], a_tracks[y]) > a_tracks[x].fps for x in p["tracks"] for y in q["tracks"]):
                together.add(frozenset((lead[p["id"]], lead[q["id"]])))
    roster.flag_conflicts(props, together)
    R.add(props)
    out = {"queries": len(in_clip[a_name]), "gallery": len(in_clip[b_name]), "sheets": len(jobs),
           **{s: sum(p.status == s for p in props) for s in ("suggested", "pending", "conflict")}}
    print(f"across: {out}")
    return out


def run_moments(R: roster.Roster, clips: list[dict], min_seconds: float = 3.0) -> dict:
    """Per-guest moments on a marked proxy tagged with roster labels, each checked against the guest's frames."""
    guests_all = [p for p in R.people() if p["kind"] == "guest"]
    out = {}
    for c in clips:
        pts, pdets = person_tracks(c, guests_all)
        if not pts:
            continue
        guests = list(pts.values())
        h = hashlib.sha256(json.dumps(sorted((t.label, sorted(t.frames.tolist())[:3]) for t in guests)).encode()).hexdigest()[:8]
        marked = c["proxy"].with_name(f"{c['name']}-roster-{h}.mp4")  # re-tagged whenever the roster changes
        if not marked.exists():
            burn.burn_ids(c["proxy"], guests, marked, masks=sam.decode_masks(pdets))
        leg = burn.legend(guests)
        fps = c["info"]["fps"]
        for label, t in pts.items():
            if t.seconds < min_seconds:
                continue
            start = max(0.0, t.first / fps - 1.0)
            end = min(c["info"]["duration"], (t.last + 1) / fps + 1.0)
            sub = PROJECT / "subclips" / f"{c['name']}-{h}-{label.strip('#')}.mp4"
            if not sub.exists():
                sub.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:.3f}", "-i",
                                str(marked), "-t", f"{end - start:.3f}", "-c:v", "libx264", "-preset", "veryfast",
                                "-crf", "22", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
                                "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:v", "+bitexact", str(sub)],
                               check=True)
            try:
                r = spark.person_moments(sub, label, leg, effort="medium", max_usd=0.3)
            except spark.SparkNoAnswer as e:
                out[f"{c['name']} {label}"] = {"error": str(e)}
                continue
            checked = moments.check_person_moments(label, r.data["moments"], pts, offset_s=start,
                                                    duration_s=c["info"]["duration"])
            out[f"{c['name']} {label}"] = {"span_s": [round(start, 2), round(end, 2)], "usd": round(r.usd, 4),
                                          "summary": r.data["summary"], "moments": checked}
            files.delete(sub)
    statuses: dict[str, int] = {}
    for v in out.values():
        for m in v.get("moments", []):
            statuses[m["check"]["status"]] = statuses.get(m["check"]["status"], 0) + 1
    print(f"moments: {len(out)} guests, {sum(len(v.get('moments', [])) for v in out.values())} moments, {statuses}")
    return {"by_guest": out, "status_counts": statuses}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stages", nargs="*", default=["prepare", "eval"])
    ap.add_argument("--efforts", default="low,medium")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--accept-suggested", action="store_true")
    args = ap.parse_args()
    start = cache.spent()
    report_path = ROOT / "docs" / "day3-roster.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    report["date"] = time.strftime("%Y-%m-%d %H:%M %Z")

    clips = [load_clip(n, s) for n, s in CLIPS.items()]
    report["clips"] = {c["name"]: {"start_s_in_source": CLIPS[c["name"]], "tracks": len(c["tracks"]),
                                   "guests": sum(t.kind == "guest" for t in c["tracks"]),
                                   "eligible": sum(roster.eligible(t) for t in c["tracks"]),
                                   "sam_usd": round(c["windowed"].usd, 4),
                                   "still_saturated": c["windowed"].saturated_spans()} for c in clips}
    print({k: {kk: v[kk] for kk in ("tracks", "guests", "eligible", "sam_usd")} for k, v in report["clips"].items()})

    if "eval" in args.stages:
        report["eval"] = run_eval(clips, args.efforts.split(","), args.workers)

    R = roster.Roster(PROJECT / "roster.json")
    if {"within", "across", "moments"} & set(args.stages):
        fill_roster(R, clips)
    if "within" in args.stages:
        report["within"] = run_within(R, clips, args.workers)
    if args.accept_suggested:  # dev run only: stands in for the human's "accept all suggested" click
        report.setdefault("accepted_by_script", {})["after_within"] = R.accept_suggested(by="script")
    if "across" in args.stages:
        report["across"] = run_across(R, clips, args.workers)
        if args.accept_suggested:
            report["accepted_by_script"]["after_across"] = R.accept_suggested(by="script")
    if {"within", "across", "moments"} & set(args.stages):
        people = R.people()
        report["people"] = {"total": len(people), "guests": sum(p["kind"] == "guest" for p in people),
                            "in_both_clips": sum(len(p["clips"]) > 1 for p in people),
                            "tracks": len(R.tracks)}
        print(f"people: {report['people']}")
    if "moments" in args.stages:
        report["moments"] = run_moments(R, clips)
    R.save()

    report["spend"] = {"this_run_usd": round(cache.spent() - start, 4), "ledger_total_usd": round(cache.spent(), 4)}
    report_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"this run: ${cache.spent() - start:.4f} · ledger total: ${cache.spent():.4f}")
    if cache.spent() - start > RUN_CAP_USD:
        print(f"WARNING: run spend above ${RUN_CAP_USD}")


if __name__ == "__main__":
    main()
