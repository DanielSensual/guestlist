# HANDOFF — Guestlist

Read this first in every new session. Update it at the end of every session.

## Status
- **2026-10-26 (Day 0/1, Claude Opus 5.5 in the planning session):** skeleton + Meta API clients built and the Day-1
  spike done end to end on a 60 s dev proxy. **GO on budget** — the whole demo set projects to ~$8 of the $150 credit.
- **2026-10-26 (Day 2, same session, a day ahead of plan):** public repo https://github.com/DanielSensual/guestlist
  (history pushed with its original dates; the dev clip's file name was scrubbed first because it names a third
  person). Built windowed SAM tracking (beats a 16-id cap we found), tracks with review signals, roster thumbnails +
  contact sheets, and the **marked proxy**: Spark now names people by our track tags, and every claim is checked
  against SAM. Day-2 spend $0.41.
- **2026-10-26 (Day 3, same session):** roster built: geometry fragment-linking, Spark re-identification sheets
  (image input), a **known-answer eval** that set the trust thresholds, cross-clip matching with a conflict check,
  per-guest moments on a roster-tagged proxy, and the roster review page (FastAPI + HTMX). Gate verdict: see
  "Day-3 gate" below. Not yet: per-person reels, ledger, consent engine, Railway app, demo footage.

## Setup
```bash
cd ~/Projects/guestlist
uv venv --python /opt/homebrew/bin/python3.13 .venv && source .venv/bin/activate   # 3.13: opencv 5 + numpy 2.5 OK
uv pip install -e ".[test]" -e ~/Projects/Websites/Bots/ghostai-video-editor
(cd tools/sam-decode && npm ci)          # fast mask decoder (Node)
python -m pytest                         # 36 tests, offline, ~3 s
ln -s "/path/to/private/dev clip.mp4" .cache/dev-clip.mp4   # dev footage stays out of the repo
python scripts/spike_day1.py             # fully cached now: re-runs cost $0
python scripts/day2_tracks.py            # fully cached now; writes docs/day2-tracks.json + renders/day2/ (local)
python scripts/day3_roster.py prepare eval within across moments --accept-suggested   # cached; projects/dev/ (local)
python -m guestlist.app --project projects/dev   # roster review at http://127.0.0.1:7788 (launch config "guestlist-roster")
```
`--accept-suggested` makes the dev run stand in for the human's "Accept all suggested" click (recorded as
`decided_by: "script"`); the app records `"human"`.
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

## Day-3 results (`docs/day3-roster.json`; clips `spike60` = source 30–90 s, `later60` = 120–180 s)

**Can Spark tell people apart? Known-answer eval** (`roster.eval_cases`): 29 long tracks cut in two around a
1 s hole; the sheet shows the first half as QUERY and, as candidates, the true second half plus up to 5 tracks on
screen *at the same time* as it (so provably someone else). Each case is asked twice: truth present / truth
removed (right answer = none). Muse Spark 1.3, image input, low effort, ~0.6¢ a sheet:

| confidence ≥ | found (truth present) | wrong person picked | false match (truth absent) |
|---|---|---|---|
| any | 21/29 | 7 | 21/29 |
| 0.7 | 17/29 | 5 | 11/29 |
| 0.8 | 15/29 | 2 | 4/29 |
| **0.9** | **9/29** | **1** | **0/29** |

→ `SUGGEST = 0.9` (pre-selected, one click), `REVIEW = 0.7` (shown, not pre-selected), below that dropped.
Spark nearly always picks *someone* when the person is absent; only its top confidence is informative. Medium
effort was no better (and once burned all 8,000 output tokens on reasoning → `SparkNoAnswer`, never cached).
Before two fixes the same eval had 15/29 false matches at ≥ 0.8: (1) the crop picker preferred the biggest boxes,
which are SAM's glitches where a dancer's box swallows the partner (masks filled 11–28 % of them) — size now counts
only up to the track's 75th percentile; (2) crops are brightened for the person's mask but the surroundings are
dimmed from the *original*, so the partner no longer lights up as brightly as the query.

**Roster run** (`within across moments --accept-suggested`):

| Stage | Result | $ |
|---|---|---|
| Within-clip | 141 eligible tracks (≥ 1 s, ≥ 1 % of frame) → 88 had geometry candidates → 88 sheets: Spark said none 19×, **2 suggested** (both handovers ≤ 1.1 s apart, look right), **27 pending**, ~40 below 0.7 dropped | 0.44 |
| Across clips | 16 guests (≥ 3 s) per clip, 8 per sheet → 32 sheets: **6 suggested** (incl. the man at 0.97), 3 pending, **3 conflict** | (in the same $2.21 `same_person` total) |
| People | 212 tracks → 204 people: 47 guests, 157 crowd; 5 people span both clips after the scripted accepts | — |
| Per-guest moments | 31 guests (≥ 3 s), each a sub-clip of a proxy re-tagged with roster labels → **85 moments: 76 supported, 8 review, 1 contradicted** (Spark named #5 at 30–33 s; #5 wasn't on screen) | 0.51 |

- **The conflict check earned its place**: Spark matched *three* different women in black dresses from clip 1 to the
  woman in clip 2 (0.98, 0.87, 0.72). The two wrong ones dance on screen together with the right one, so all three go
  to a human; accepting the right one (`#2 = #28`) now rejects the other two automatically (`decided_by: "rule"`).
  Verified in the browser on a copy of roster.json; the dev roster is left **unreviewed** for Daniel.
- **Review page** (`python -m guestlist.app`, FastAPI + Jinja + HTMX, no client state): conflicts first, then
  suggested, then pending; each card shows both crops, Spark's evidence, gap/movement for within-clip pairs, a link
  to the exact sheet Spark saw, and Same person / Different. Guests grid with name + confirm; crowd collapsed.
- **Day-3 spend $2.99** (`same_person` $2.21 — the eval was most of it, `person_moments` $0.51, SAM for clip 2 $0.26;
  $0.13 of it was a mistaken second cross-clip pass that was rolled back).

### Day-3 gate
My first read was "tracking + roster hold on the worst footage we'll ever give it". **Astra rejected that as
unsupported, and it's right**: only the two foreground dancers come through cleanly, 212 tracks became 204 people,
and the roster is unreviewed. What the dev clips do show: lit, distinctly dressed people are re-identified at
0.9–0.98 and correctly; dark crowd silhouettes are not reliably re-identifiable by appearance. **The gate moves to
Day 4 on real footage** (below).

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
    action. ✅ Day 3: per-guest prompt on a sub-clip of their span gives 2–6 s moments.
12. **Muse Spark re-ID is overconfident**: it nearly always picks someone; only confidence ≥ 0.9 is informative on
    dark footage (eval above). Medium reasoning was no better than low and can spend the whole output budget thinking.
13. **The biggest boxes in a track are usually SAM glitches** (one dancer's box swallowing the partner). Thumbnails
    and re-ID crops no longer reward size above the track's 75th percentile.
14. **"Right time, wrong person" is not caught yet.** For some background guests Spark's per-guest summary describes
    the main couple: the presence check only proves the tag was on screen. Day-4 fix that also feeds the reels:
    **follow-crop sub-clips** (crop to the guest's smoothed box) so the guest is the subject of the frame.
15. Conflicts need a rule, not just a flag: accepting one side rejects the other (implemented).

## Spend ledger (Meta credits: $150; plan ceiling $107, hard stop $115)
| date | what | $ |
|---|---|---|
| 2026-10-26 | SAM concept 60 s + box re-track; Spark 20 s + 60 s; transcribe 60 s | 0.26 |
| 2026-10-26 | Day 2: 16-id cap test ($0.02), windowed SAM 60 s ($0.32), marked Spark log + decoy control ($0.07) | 0.41 |
| 2026-10-26 | Day 3: SAM clip 2 ($0.26), re-ID eval + within + across sheets ($2.21), per-guest moments ($0.51) | 2.99 |
| **total** | | **3.67** |

## Astra gate review #1 (`docs/reviews/astra-gate1.md`, GPT-6 Astra, ~$0.1)
**Verdict: continue with narrower scope, but the Day-3 gate is NOT passed** — it needed the real footage. Scope:
*editor-assisted guest reels for small, consenting events*; human-confirmed identity, coverage accounting, exclusion
by shot removal. Defer blur-as-privacy, SFace, voice and title cards. Its sharpest points, and what was done:

| Astra's point | Done |
|---|---|
| The "known-answer" eval uses SAM for both positives and negatives (a split track can hide an id switch; simultaneous tracks can be one person); thresholds were tuned on the same 29 cases | **Not fixed — needs labels.** Hand-label the eval cases and hold out an untouched take of the demo footage before quoting accuracy. Until then: "≥ 0.9 was right 9 of 10 times on 29 SAM-derived cases" — not a calibrated probability. |
| "supported" moments only prove presence | Renamed: per tag `present/weak/absent`, overall `presence_ok/review/contradicted/bad_time`. The subject of a moment must now cover half of it; `unmarked`-only → review; times are bounds-checked. (`docs/day2-*.json`/`day3-*.json` predate the rename: `supported` there = `presence_ok`.) |
| `stitch`: one shared frame can authorize an irreversible join | ≥ 3 shared frames and a 0.1 IoU margin over any rival, else the seam stays open (`made: False`) for the roster. On the dev clips: 0 ambiguous, 9 of 129 seams thin. **The dev roster predates this guard — regenerate it (delete `projects/dev/roster.json`) before re-running.** |
| `cut_window` can reuse stale cuts; overlap ≥ window loops | Cuts live under `windows/<stem>-<sha8>/`; `plan_windows` rejects overlap ≥ window. |
| Conflicts: bulk accept bypasses rules; a ruled-out pair can still be accepted | `accept_suggested` goes through `decide`; `decide` refuses a pair whose rival is accepted (UI shows why). Shared-query / transitive cannot-link not done yet. |
| Confirmation silently extends to new fragments; labels renumber | Confirmation is now a snapshot of the exact tracks; a later merge un-confirms. Stable person ids + versioned moments: not yet. |
| Seconds double-count across cameras | Not yet: split camera-seconds vs event-time coverage when cameras are synced (Day 4). |
| "$8.40 demo" | Wrong: 2 × 20 min at 12 fps = $5.76 per pass, ×2.2 when crowded ≈ **$12.7** before re-tracks, plus per-guest Spark calls. Still far inside $150. |
| "Keeps it legal in BIPA states" | Removed from PLAN.md; replaced with "a design choice, not a legal determination". |

## Next step — Day 4 (the real gate)
1. **Daniel: shoot the gate footage** (Astra's spec, replaces the 20-min plan for now): **two synchronized cameras,
   ~3 min each, plus a second untouched take held out**. Soft light, locked exposure, ordinary but distinguishable
   outfits, a sync clap, 5–6 consenting friends with a one-line release. Include on purpose: one similar-outfit pair,
   an exit and re-entry, a couple overlapping, a back-facing turn, a dim passage, a background-only moment. Give camera
   2 genuinely different coverage. Withdrawal: stage it only with real, continuing permission to show the demo.
2. **Gate (end of Day 4):** all guests correctly grouped after ≤ 10 min of review (time it); ≥ 95 % tracking recall
   on hand-annotated visible people sampled once a second; no unresolved identity switch inside selected reel
   intervals; one playable per-person reel with correct source timecodes. Fail, or still no footage → pivot.
3. **Ledger → reel:** seed an *expected guest list* by hand (tracking can't count people it never saw); ledger states
   "not detected" / "unreviewed" / "excluded"; per-guest **follow-crop** sub-clips (crop to the smoothed track box)
   feeding both Spark moments (fixes finding 14) and the GhostCut reel render; FCPXML export.
4. Hand-label the eval cases on the new footage; re-measure thresholds on the held-out take.
5. Then Day 5–6 per Astra: show Meta's contribution plainly (SAM tags → Spark structured proposal → source-linked
   check), stable person ids, fail-closed exclusion (remove shots, invalidate served outputs, block uncertain exports).
6. Daniel: track (Indie recommended), SFace question (finding 7 — Astra says defer), Spend Limit on dev.meta.ai.
