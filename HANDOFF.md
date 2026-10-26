# HANDOFF — Guestlist

Read this first in every new session. Update it at the end of every session.

## Status
- **2026-10-26 (Day 0/1, Claude Opus 5.5 in the planning session):** skeleton + Meta API clients built and the Day-1
  spike done end to end on a 60 s dev proxy. **GO on budget** — the whole demo set projects to ~$8 of the $150 credit.
  Not yet: GitHub repo (name `guestlist` is free under DanielSensual; waiting on Daniel's OK), track/roster code, app.

## Setup
```bash
cd ~/Projects/guestlist
uv venv --python /opt/homebrew/bin/python3.13 .venv && source .venv/bin/activate   # 3.13: opencv 5 + numpy 2.5 OK
uv pip install -e ".[test]" -e ~/Projects/Websites/Bots/ghostai-video-editor
(cd tools/sam-decode && npm ci)          # fast mask decoder (Node)
python -m pytest                         # 14 tests, offline, <2 s
python scripts/spike_day1.py             # fully cached now: re-runs cost $0
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

## Findings that change the code / plan
1. **`meta_sam_parser` (Python) decodes every mask while parsing at ~1 s/mask** (pure-Python range decoder) → a 60 s clip took ~30 min to parse. Fixed: `sam.parse` is a regex parser (1,866 detections in 0.01 s) that keeps masks encoded; `sam.decode_masks()` bulk-decodes through Meta's JS decoder (`tools/sam-decode/decode.mjs`, **12.5 ms/mask**, verified pixel-identical to the Python decoder). Use `Detection.mask_array()` only for one-offs.
2. **Mask rasters are capped at 1024 px on the long side** — a 1105×350 box comes back as a 1024×324 raster. `sam.fit_to_box()` scales it back (nearest neighbour). Overlay verified visually at `renders/spike-mid-overlay.png` (local only — dev footage, not for the repo).
3. **SAM confidence `c` is constant per object across frames** (a track-level score), not per-frame. Low-confidence routing for the review queue must use other signals too: mask area vs box area, sudden box jumps, short track length, track gaps.
4. **SAM ids are stable within a clip but drop on exit/re-entry** (per docs); background people come and go as new ids → the roster must merge fragments *within* a clip, not just across cameras.
5. **Spark labels people P1/P2 by appearance; SAM labels them 0/1.** Linking them is the core roster problem. Best idea for Day 3 (also a strong "unexpected capability" story): **burn the SAM track ids/outlines into a second proxy and give Spark that video**, so its event log refers to SAM's ids directly (visual prompting), then confirm by human.
6. Transcribe gives turn-level timestamps only; music-heavy audio gives little. Keep it optional (toasts/speeches only).
7. GhostCut's recap already has YuNet + SFace face embeddings (`recap/faces.py`; same-person ≥ ~0.41, strangers ≤ ~0.32) and person exclusion (`casting.py`/`select.py`). **Decision for Daniel:** the plan says "no biometric database" — we could still use SFace *transiently* to propose roster merges (never stored), or stick to Spark-only proposals + human confirm.

## Spend ledger (Meta credits: $150; plan ceiling $107, hard stop $115)
| date | what | $ |
|---|---|---|
| 2026-10-26 | SAM concept 60 s + box re-track; Spark 20 s + 60 s; transcribe 60 s | 0.26 |
| **total** | | **0.26** |

## Next step — Day 2 (Oct 28 per plan; we're a day ahead)
1. `src/guestlist/tracks.py`: per clip → SAM concept pass (`person`) → `Track` objects (clip, sam id, frames, boxes, mask-area ratio, gaps, quality signals), drop tracks under ~1 s / tiny area as "crowd", keep them listed for consent checks.
2. Track thumbnails: best frame per track (largest box × centrality × sharpness), crop from the proxy, contact sheet per clip.
3. The "burned-id proxy" (finding 5): draw SAM outlines + ids onto a copy of the proxy; run Spark's event log on it with a prompt that refers to people by those ids. Compare against the plain-proxy log on the 60 s spike clip.
4. Daniel: shoot the demo footage (plan §6 — 20-min staged party, 2 cameras, 5–6 consenting friends with a one-line release, one of whom will "withdraw consent" on camera).
5. Daniel: confirm the GitHub repo name `guestlist` (free) so we can push with dated history; confirm track (Indie recommended).
