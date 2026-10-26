# HANDOFF — Guestlist

Read this first in every new session. Update it at the end of every session.

## Status
- **2026-10-26 (Day 0/1, Claude Opus 5.5 in the planning session):** skeleton + Meta API clients built and the Day-1
  spike done end to end on a 60 s dev proxy. **GO on budget** — the whole demo set projects to ~$8 of the $150 credit.
- **2026-10-26 (Day 2, same session, a day ahead of plan):** public repo https://github.com/DanielSensual/guestlist
  (history pushed with its original dates; the dev clip's file name was scrubbed first because it names a third
  person). Built windowed SAM tracking (beats a 16-id cap we found), tracks with review signals, roster thumbnails +
  contact sheets, and the **marked proxy**: Spark now names people by our track tags, and every claim is checked
  against SAM. Day-2 spend $0.41. Not yet: roster merge/confirm, per-person reels, consent engine, app, demo footage.

## Setup
```bash
cd ~/Projects/guestlist
uv venv --python /opt/homebrew/bin/python3.13 .venv && source .venv/bin/activate   # 3.13: opencv 5 + numpy 2.5 OK
uv pip install -e ".[test]" -e ~/Projects/Websites/Bots/ghostai-video-editor
(cd tools/sam-decode && npm ci)          # fast mask decoder (Node)
python -m pytest                         # 28 tests, offline, <3 s
ln -s "/path/to/private/dev clip.mp4" .cache/dev-clip.mp4   # dev footage stays out of the repo
python scripts/spike_day1.py             # fully cached now: re-runs cost $0
python scripts/day2_tracks.py            # fully cached now; writes docs/day2-tracks.json + renders/day2/ (local)
```
Key: `~/.config/ghostai/meta-api.env` (`MODEL_API_KEY=`). Never in the repo. The ledger is `.cache/spend.jsonl`
(`guestlist.meta.cache.spent()`); `GUESTLIST_BUDGET_USD` (default 115) is a hard stop checked before paid calls.

## Day-1 measurements (`docs/spike-day1.json`)
Proxy: 720×1280, 12 fps CFR, H.264 CRF 26, faststart, 60 s = **11.8 MB** (720 frames). Uploads: Files API, `purpose=user_data`, 7-day expiry, deduped by sha256, deleted after the spike.

| Call | Result | Cost | Wall clock |
|---|---|---|---|
| SAM 3.1 concept `person`, 60 s | 16 objects: both dancers tracked **all 720 frames** (conf 0.95 / 0.88) + 14 short-lived background people (conf 0.71–0.82, 5–70 frames, 0.9–6 % of frame) | **$0.144** (720 frames) | 44.7 s (first frame 5.4 s) |
| SAM 3.1 box re-track, forward from frame 360 | 360/360 frames, conf 0.96 | $0.072 | 32.7 s |
| Spark 1.3 event log, 20 s | 5,866 in / 1,527 out, 5 events | $0.014 | 12.5 s |
| Spark 1.3 event log, 60 s (effort medium) | 16,766 in / 2,242 out (1,377 reasoning); 2 people described accurately, 7 well-timed events | **$0.030** | 18.8 s |
| Voice Transcribe DIARIZATION, 60 s | 2 turns, 1 speaker (music clip) | $0.003 | — |
| **Total Day 1** | | **$0.26** | |

- **Spark video = ~272 input tokens per second of video** (+ ~416 fixed), measured from two real generations (20 s vs 60 s).
  → ~$0.34/hour of footage on input. The `POST /responses/input_tokens` endpoint does **not** count video (171 tokens for 20 s and 60 s alike) — don't use it for estimates.
- **SAM = $0.20 per 1k frames** confirmed via `usage.video_frames_processed`. A 20-min clip at 12 fps = $2.88 per concept pass. Up to 15,000 frames (~20 min at 12 fps) per request; 16 objects/frame max.
- **Projection, demo set (2 cams × 20 min):** SAM ~$7.20 (incl. 25 % re-tracks) + Spark ~$1.20 ≈ **$8.40**. Budget headroom is huge → we can afford 24 fps SAM passes or several Spark passes per clip if quality needs it.
- **Rate limits seen in headers:** SAM **60 requests/min** (not the 3,000 the docs list), Spark 3,000 RPM / 4M TPM.

## Day-2 results (`docs/day2-tracks.json`, same 60 s club clip)

| | Day-1 single pass | Day-2 windowed (10 s windows, 1 s overlap, split when full) |
|---|---|---|
| Requests / frames billed / $ | 1 / 720 / $0.144 | 19 (13 kept + 6 split) / 1,584 / **$0.317** |
| Tracks found | 16 (the cap) — **0 new after frame 158** | **111** (28 guests, 83 crowd) — 80 start after frame 160 |
| The two dancers | 100 % / 99.2 % of frames | 100 % / 99.2 % — stitched across 12 seams, IoU ≥ 0.66 |
| Still saturated at 5.5 s windows | — | 4 spans (packed floor) → reported, not hidden |

- **Thumbnails + contact sheet:** 111 crops in ~3 s (one sequential decode pass); best frame = big × central × not
  edge-clipped × relative sharpness × (1 + frontal face). Face *detection* only (YuNet via GhostCut) — no embeddings.
  `renders/day2/spike60-contact.png` (local). It surfaces real junk for review, e.g. a curtain SAM took for a person.
- **Marked proxy → Spark (the Day-1 finding-5 experiment): it works.** Outlines + `#n` tags burned in; schema enum
  restricts person labels to our tags + `unmarked` (Meta's strict structured output accepts `enum`). Spark described
  #1/#2 correctly (cap + light shirt / blonde ponytail + black dress), listed all 28 tags with **first-seen times
  matching SAM's track starts to a median 0.17 s (26/28 within 1 s)**, and all 8 events pass the geometry check.
  **Decoy control:** a 29th tag in the legend that is drawn on nobody was never used (people or events). $0.039/call.
- Moment checks (`moments.py`): a tag is *supported* when on screen ≥ 1 s of the event (or half a shorter one); else
  *weak* (review) / *unsupported* or *unknown_tag* (contradicted). Requiring half of every event was too strict for
  background dancers in Spark's 6–8 s events.

## Findings that change the code / plan
1. **`meta_sam_parser` (Python) decodes every mask while parsing at ~1 s/mask** (pure-Python range decoder) → a 60 s clip took ~30 min to parse. Fixed: `sam.parse` is a regex parser (1,866 detections in 0.01 s) that keeps masks encoded; `sam.decode_masks()` bulk-decodes through Meta's JS decoder (`tools/sam-decode/decode.mjs`, **12.5 ms/mask**, verified pixel-identical to the Python decoder). Use `Detection.mask_array()` only for one-offs.
2. **Mask rasters are capped at 1024 px on the long side** — a 1105×350 box comes back as a 1024×324 raster. `sam.fit_to_box()` scales it back (nearest neighbour). Overlay verified visually at `renders/spike-mid-overlay.png` (local only — dev footage, not for the repo).
3. **SAM confidence `c` is constant per object across frames** (a track-level score), not per-frame. Low-confidence routing for the review queue must use other signals too: mask area vs box area, sudden box jumps, short track length, track gaps.
4. **SAM ids are stable within a clip but drop on exit/re-entry** (per docs); background people come and go as new ids → the roster must merge fragments *within* a clip, not just across cameras.
5. **Spark labels people P1/P2 by appearance; SAM labels them 0/1.** ✅ Solved on Day 2 by the marked proxy (above):
   Spark adopts our tags, so there is nothing to link — only claims to check.
6. Transcribe gives turn-level timestamps only; music-heavy audio gives little. Keep it optional (toasts/speeches only).
7. GhostCut's recap already has YuNet + SFace face embeddings (`recap/faces.py`; same-person ≥ ~0.41, strangers ≤ ~0.32) and person exclusion (`casting.py`/`select.py`). **Decision for Daniel:** the plan says "no biometric database" — we could still use SFace *transiently* to propose roster merges (never stored), or stick to Spark-only proposals + human confirm. (Day 2 uses YuNet *detection* only, for thumbnails.)
8. **SAM 3.1 hands out at most 16 object ids per request** (both the 60 s pass and a separate 10 s window stopped at
   exactly ids 0–15, with people still visible afterwards; the docs only mention 16 objects per *frame*). Fixed by
   `windows.py`: frame-exact, bit-exact window cuts of the proxy (re-cuts hit the cache), 4 requests in parallel, full
   windows split down to 5 s, stitched by mean box IoU on the shared second. Cost ≈ 2.2× a single pass on a packed
   floor, ~1.1× on a quiet one. Windows still full at the minimum go into the coverage ledger as "may have missed people".
9. **Track fragmentation is the next real problem**: 111 tracks for maybe 30–40 real people. Ids drop on occlusion /
   re-entry inside a window. Merging fragments is roster work (Day 3); the per-track guest/crowd split is provisional.
10. **SAM boxes jump on the lead couple 1–4 times a minute** (e.g. frame 590: #1's box widens from 151 to 441 px in
    one frame) — most likely the mask briefly taking in the partner's arm; not yet checked frame by frame. The per-frame jump list feeds the review queue; the track flag `unstable` needs > 0.2 jumps/s.
11. Spark's events are coarse (6–8 s) when asked to cover the whole clip; it names background tags by position, not
    action. Per-person moments need a per-tag prompt or shorter clips (Day 3).

## Spend ledger (Meta credits: $150; plan ceiling $107, hard stop $115)
| date | what | $ |
|---|---|---|
| 2026-10-26 | SAM concept 60 s + box re-track; Spark 20 s + 60 s; transcribe 60 s | 0.26 |
| 2026-10-26 | Day 2: 16-id cap test ($0.02), windowed SAM 60 s ($0.32), marked Spark log + decoy control ($0.07) | 0.41 |
| **total** | | **0.68** |

## Next step — Day 3 (Oct 29 per plan; the gate day)
1. **Roster, within a clip:** propose fragment merges (track A ends, B starts nearby within a few seconds at a
   similar size) and ask Spark on the marked proxy "which tags are the same person?" (schema: pairs of our tags +
   evidence + confidence), then check each proposal mechanically (never on screen at the same time; plausible gap).
2. **Roster, across cameras:** same question over two marked proxies of the same moment (or a side-by-side marked
   contact sheet as an image), human confirms in the grid.
3. Per-person moments: one Spark call per guest tag ("moments for #3 only") on the marked proxy, checked by `moments.py`.
4. Minimal roster UI (track grid from the contact-sheet crops, merge/confirm buttons) — Day 6 wraps it into the app.
5. **Gate:** all of the above on the real demo footage. Astra review #1 (diff + `docs/day2-tracks.json`).
6. Daniel: **shoot the demo footage** (plan §6 — 20-min staged party, 2 cameras, 5–6 consenting friends with a one-line
   release, one of whom will "withdraw consent" on camera). Until then everything runs on the club dev clip.
7. Daniel: confirm the track (Indie recommended); decide the SFace question (finding 7); set a Spend Limit on dev.meta.ai.
