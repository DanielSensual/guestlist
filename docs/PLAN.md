# Meta Global AI Developer Hackathon — build plan

**Status:** DRAFT for Daniel's approval · written 2026-10-26 by Claude Fable 5.1 (ideas) with GPT-6 Astra as the second slate and hostile reviewer · execution is planned for Claude Opus 5.5 in a fresh session.
**Deadline:** submissions due **Tue Nov 4, 9:00 PM ET** (9 days). Judging Nov 4–8. Live finals Nov 9.
**Rubric:** Impact 30 · Use of Meta AI Tooling 25 · Demo 25 · Technical Depth 20.

---

## 1. The bet

**Working title: "Guestlist"** — *the event-footage system that knows who is in every frame. Every guest gets their own film. Anyone can opt out.*

Drop two cameras' worth of event footage (wedding, dance night, kids' recital, church, team party). SAM 3.1 tracks every person through every clip. You name the tracks on a roster — Spark proposes "these three tracks are the same person", you confirm. Then:

1. **Everyone gets a film.** For each person on the roster, Spark picks their best moments (video-in, structured JSON), GhostCut's recap engine cuts a 20–30 s beat-synced reel framed on *them* (track boxes drive the crop, including a 9:16 version), and they get a link.
2. **A coverage ledger.** A table of who got how many moments and — the part nobody else builds — **who was missed**. Click a missed guest and the system shows the overlooked moment it found and generates their reel.
3. **Consent is a switch.** Mark a guest "must not appear" and three things update: their reel is withdrawn, the public recap re-cuts around them (alternate shot when the shot still works without them, feathered mask blur from SAM masks when it doesn't), and every low-confidence frame (mirrors, reflections, backs of heads, partial occlusion) lands in a review queue instead of being silently blurred or silently published.

**Why this one** (over the 15 other ideas in §3): it is Daniel's firsthand pain (he cut one clip per couple every week for a dance night and keeps an `--exclude-clip person-to-leave-out` flag in GhostCut for exactly this), SAM 3.1 video tracking is the *core primitive* rather than a garnish, the demo has two lean-forward moments ("the recap left her out — found her — here's her film" and "withdraw consent — three deliverables change"), and it's sellable the week after: venues, dance schools, youth sports, schools, churches, wedding filmmakers.

**Theme:** Build for Your World. **Track:** see §8 — Indie unless Daniel already applied as Startup.

**Design principles the judges should see in the README**
- No face-recognition database. Tracks are grouped by a human with Spark proposing matches from thumbnails; nothing biometric is stored. (Keeps it legal in BIPA states and honest about reliability.)
- Mechanical checks are labeled as mechanical (durations, source timecodes, "this person's mask never appears in the public recap"); semantic judgments are labeled with confidence and a review status. Never present model agreement as proof.
- Ends in the editor's NLE: FCPXML/OTIO export of every reel, plus the rendered MP4s.
- Pre-existing open-source pipeline (GhostCut, MIT, public since July 2026) is disclosed; the new hackathon work (SAM tracker, roster, ledger, consent engine, web app) is clearly marked.

---

## 2. Three hero features (must work live, in priority order)

| # | Feature | Meta API behind it | What the judge sees |
|---|---|---|---|
| 1 | **Roster** — every person tracked through every clip, grouped into people | `sam-3.1` concept prompt `"person"` per proxy clip → per-frame boxes + masks + confidence; `muse-spark-1.3` image input compares track thumbnails and proposes merges (JSON) | A grid of tracked people with thumbnails and timelines; one click confirms a merge |
| 2 | **Everyone's film + the ledger** — a per-person reel and a coverage table | `muse-spark-1.3` video input per clip with the track timeline as context → structured `moments[]` per person (what happened, why it matters, score); GhostCut recap engine renders; `muse-image-1.0` title card | "Maria: 7 moments, 24 s reel. Jordan: 0 moments — **missed** → found one at 41:12 → reel generated" |
| 3 | **Consent switch** — exclude a person safely | SAM masks → feathered blur (existing modesty-blur recipe) or alternate-shot selection; Spark judges "does the shot still work without them?"; low-confidence frames → review queue | Flip one toggle; reel withdrawn, recap re-rendered, review queue shows the mirror reflection it wasn't sure about |

Supporting (only if ahead of schedule): `muse-voice-transcribe-1.0` DIARIZATION to attach toasts/speeches to the speaker's reel; 9:16 auto-reframe following the track box; Muse Code used for scaffolding (mention in submission).

Explicitly **out of scope**: billing, multi-user accounts, arbitrary codec ingestion (proxies only), a timeline UI, cross-event identity, any "guaranteed anonymous" claim.

---

## 3. How we got here (two slates, 16 ideas)

**Fable slate:** Ghost Editor (the editor that watches your footage) · PersonCut (one clip per guest) · ListingLens (home-tour video → whole listing) · Ghost Dailies (script supervisor + DIT in a box) · Ghost Scout (location walkthrough → shot plan) · DroneInspect (Push the Frontier) · The Agent That Watches (video intake for trades) · MoveMirror (dance coach, Push the Frontier).

**Astra slate (independent, round 1):** Cut Contracts (client notes → executable constraints → inspectable timeline repair, scored 90) · ConsentCut (88) · Moment Receipts (per-participant reels + coverage ledger, 87) · LightLoop (closed-loop studio lighting, Frontier, 86) · ClearPath Rehearsal (venue aisle widths, Frontier, 84) · RoomProof (listing claims vs. walkthrough evidence, 82) · MicMap (mic placement experiment, Frontier, 81) · ScopeWitness (before/after site walkthroughs → change order, 80).

**Astra's round-1 bet:** Cut Contracts, Indie — "the editor that turns client notes into tests and shows its work." Kill criterion: if structured instructions can't change and validate a real timeline by day 3, pivot to RoomProof.

**Fable's synthesis:** Astra is right that "another automatic editor" (my Ghost Editor) is what 50 other teams will submit, and right that Indie is the safer track. But Cut Contracts is abstract on screen — its best moment is a diff, and the SAM use is a garnish. The strongest thing on either slate is the **merge of Moment Receipts + ConsentCut + my PersonCut**: same SAM tracks power inclusion (your film) and exclusion (opt out), the coverage ledger is the twist that separates it from auto-highlights, and both demo beats are visceral. Cut Contracts stays as the **pivot** if tracking doesn't hold on real footage by day 3 (it reuses GhostCut + the QA pass and needs no SAM).

Astra's round-2 verdict on this pick is in §10.

---

## 4. Verified Meta API facts (read from dev.meta.ai docs, 2026-10-26)

- **Auth/base:** `https://api.meta.ai/v1`, Bearer `MODEL_API_KEY`. OpenAI SDK works (Responses + Chat Completions); Anthropic Messages format too. Use a `developer` message, not `system`. Key verified (`GET /models` → 200, 9 models). Key file: `~/.config/ghostai/meta-api.env` (never in the repo).
- **Video into Spark:** upload via Files API (`POST /v1/files`, `purpose=user_data`, optional `expires_after` 1 h–30 d) then `input_video`/`input_file` with `file_id`; or `video_url` (public/base64). Inline cap 50 MB. MP4 (`video/mp4`) — **faststart** (`-movflags +faststart`). Spark reads embedded audio too. Set `max_output_tokens ≥ 4000` and `stream: true` (reasoning shares the output budget; long clips idle-timeout otherwise). Team storage cap 100 GiB; uploads don't expire unless told to — set `expires_after`.
- **Audio:** Spark 1.3 audio understanding is degraded — use Spark 1.2 or Voice Transcribe for audio.
- **SAM 3.1:** Responses API, `model: "sam-3.1"`, one user message with `input_text` + (`input_image` | `input_video`). **Concept prompt** = one short noun phrase, one concept per request (`"person"`, `"red dress"`); no lists, no negation, no commands. **Box/point prompts** use the token grammar `<Nf>id<|box;x1..y2;w;h|>` / `<|point;x;y;w;h|>` (negative points with `-`), object ids you choose, prompts on any frames; `metadata.propagation_direction` = `both|forward|backward`. Output streams one line per frame: `<Nf>id<|box;…;c=conf|><|mask;…;data=RLE|>`. `w,h` must be the displayed dimensions after rotation. Python/TS helpers exist (`build_object_prompt`, mask decoding) — see `docs/sam/client-libraries`. Minimum-frame billing per request.
- **Transcribe:** `POST /v1/asr/transcribe`, multipart `request={"mode":"DIARIZATION","model":"muse-voice-transcribe-1.0","audioEncoding":"WAV"}` + WAV mono 16-bit 16/24 kHz. Turn-level timestamps + speaker labels A/B/…; **no word timestamps** (keep Whisper for captions). 25 languages, `languageBias`, `keywords`.
- **Pricing (Standard):** Spark 1.3 $1.25 in / $4.25 out / $0.15 cached per M tokens · Wonder $4 / $20 · Image $0.01 each · Transcribe $0.18/hr · **SAM video $0.20 per 1k frames**, image $2.50 per 1k. Web search $2.50/1k. No long-context premium; prompt caching available.
- **Limits:** Spark/Wonder 3,000 RPM / 4M TPM per team; SAM 3,000 RPM; Image 150 RPM; background responses 600/min.
- **Never use `-contributor` model IDs** — they license Meta to train on the footage.
- **Unknown until the day-1 spike:** Spark video tokens per second of video; SAM max clip length/frames per request; Files API max upload size (only the 50 MB inline cap is documented).

---

## 5. Architecture

```
camera cards ──ingest──▶ 720p/12fps faststart proxies (ffmpeg, GhostCut.ingest)
      │
      ├─▶ SAM 3.1 "person" pass per proxy ──▶ tracks{clip, id, frames[], boxes, masks(RLE), conf}
      │          └─▶ thumbnails per track ──▶ Spark (image-in): "same person?" proposals ──▶ ROSTER (human confirms)
      ├─▶ Spark 1.3 video-in per clip (+ track timeline as context) ──▶ moments[] per person (JSON, structured output)
      ├─▶ (optional) Voice Transcribe DIARIZATION ──▶ speech turns → attach to roster
      │
      ├─▶ LEDGER: per person {moments, seconds, reels, missed?, consent}
      ├─▶ per-person reel: GhostCut recap engine (beat grid, motion peaks) + track-box crop (16:9 + 9:16) + Muse Image title card
      ├─▶ public recap: consent-aware selection; feathered mask blur; alternates; review queue
      └─▶ outputs: MP4s, FCPXML/OTIO, ledger.json + ledger.html, per-person share links
```

- **Core:** Python package that depends on `ghostcut` (public MIT repo at `~/Projects/Websites/Bots/ghostai-video-editor`, GitHub `DanielSensual/ghostcut`). New modules: `meta/files.py`, `meta/sam.py` (prompt builder + stream parser + RLE decode), `meta/spark.py` (video log + roster matching + moments, all structured output), `meta/transcribe.py`, `roster.py`, `ledger.py`, `consent.py`, `reels.py`.
- **App:** one Railway service — FastAPI + a worker process + Postgres (Railway) + R2 for media; HTMX/Jinja UI (roster grid, ledger table, consent toggles, review queue, downloads). Live HTTPS URL is a submission requirement. Local Mac does the heavy renders for the demo set; the live app runs the short proxy set end-to-end.
- **Caching:** every API response is cached on disk keyed by (file hash, prompt, model) so re-runs cost nothing. Analyze once, iterate on assembly for free.
- **Repo:** new public repo `DanielSensual/<name>` (name in §8), MIT, dated commits from Oct 27, `HANDOFF.md` for session handoffs, README with the disclosure line.

---

## 6. Footage and rights

Rules: the submission must be original, solely owned, free of third-party IP; everything shared is non-confidential and Meta gets a perpetual license to use the submission (marketing included). So **no client deliverables, no lead data** and no footage of people who didn't agree to be in a public demo.

Options on the Extreme SSD (rights-safe first):
1. **Shoot a 20-minute staged party on Day 2–3** — two cameras, 5–6 friends who sign a one-line release, one of whom will "withdraw consent" on camera for the demo. Honest, controllable, and the consent beat is real. **Recommended.**
2. `Dances/` and the Bachata After Dark clips — Daniel owns the footage and dancers received their public clips, but there was no release for a Meta-licensed demo. Use only with people who say yes.
3. `DanielAI-Filmmaker/`, `Europe-Trip-2026/`, talking-head batches — his own, good for dev/testing (tracking, proxies, cost), not for the "guest" story.
4. `DJI_Drone_Footage/` — his own; irrelevant to the story.

---

## 7. Budget guard ($150 credit, ~10-day window — likely expires ~Nov 5)

- Set a **Spend Limit of $150** on dev.meta.ai Billing before the first call (unverified whether one is set).
- Working estimate (to be replaced by day-1 measurements): 20 min × 2 cams at 12 fps = 28.8k frames → **$5.76 per SAM concept pass**; box-prompt re-tracks on uncertain clips ≈ $5; Spark video logging ≈ $20–40 depending on tokens/sec; roster matching (image-in) ≈ $2; transcribe < $1; images < $1. **Target ≤ $100 for dev, keep $30 for the live demo during judging.**
- The one trick: **proxies at 720p/12 fps and one concept pass per clip**; cache everything; never re-run analysis to iterate on cuts.
- Report spend in `HANDOFF.md` after every session (`x-ratelimit-*` headers + dashboard).

---

## 8. Decisions Daniel must make before Day 1

1. **Track.** Which one did you apply under? (One track per participant; the form asked.) Astra and Fable both lean **Indie** for a 9-day build — Startup invites "does it hold up in production" questions about codecs, uploads, queues and paying users. If you already applied Startup, we position Ghost AI Systems LLC as the company, keep GhostCut's public history as the production story, and you are the Representative.
2. **Footage.** Stage the party (recommended) or clear specific dancers?
3. **Name.** Working title *Guestlist*. Alternatives: *InFrame*, *Roster*, *Headcount*, *Everyone's Cut*, *Moment Receipts* (Astra's). Check the GitHub/domain collision before committing.
4. **Pivot rule.** Accept the Day-3 kill criterion: if SAM tracks + roster don't hold on real footage by end of Oct 29, pivot to Cut Contracts (reuses GhostCut + the QA pass, no SAM dependency).
5. **Execution model.** Opus 5.5 builds in a fresh session per phase (quality degrades late in long contexts); Haiku subagents for tests/grunt work; Astra reviews at the Day-3 and Day-6 gates; Fable on the demo script and the submission copy.

---

## 9. Nine-day schedule (Day 1 = Mon Oct 27 … Day 9 = Tue Nov 4)

| Day | Ship | Cut if behind |
|---|---|---|
| **1 · Oct 27** | API spike on a 60 s proxy: Files upload, SAM `"person"` pass + one box-prompt re-track, Spark video log with structured output, transcribe. **Measure tokens/sec of video, frames/request limits, latency, $.** Public repo scaffold, disclosure README, spend limit set. | — |
| **2 · Oct 28** | `meta/sam.py` + RLE decode + track thumbnails + per-clip track timelines. Shoot the demo footage. | Transcribe |
| **3 · Oct 29** | Roster: track grid UI, Spark merge proposals, human confirm. Spark moments per person (JSON). **Gate: tracking + roster hold on the real footage, or pivot.** Astra review #1. | — |
| **4 · Oct 30** | Per-person reels via the recap engine + track-box crop; ledger with missed-guest detection; FCPXML export. | 9:16 reframe |
| **5 · Oct 31** | Consent engine: exclude → withdraw reel, re-cut recap, mask blur, alternate-shot logic, review queue for low-confidence frames. | Alternate-shot logic (blur only) |
| **6 · Nov 1** | Railway app: upload → job → roster → ledger → consent → downloads; live URL; queue restart-safe. Astra review #2. | Share links (downloads only) |
| **7 · Nov 2** | End-to-end on the demo set; Muse Image title cards; captions; polish; README + architecture diagram. | Title cards |
| **8 · Nov 3** | **Shoot and cut the demo video (≤ 3 min)**; write the submission copy; fresh-clone test. | — |
| **9 · Nov 4** | Buffer + final live test; **submit by 6 PM ET** (3-hour margin). Watch the Discord for the submission form fields. | — |

Submission checklist (from the Ghost Operator run): public repo with dated commits + LICENSE detected · live HTTPS URL verified 200 · demo video under 3 min, clear audio (Daniel's ElevenLabs clone VO worked last time) · no customer data, secrets, third-party marks, or copyrighted music · Official Rules accepted on Cerebral Valley · app stays up through Nov 8.

---

## 10. Astra round-2 verdict, and the call

Astra saw both slates and **doubled down on Cut Contracts (ship name "CutPact"), Indie.** Its case: the demo is "a polished-but-wrong film becomes correct"; Spark localizes events and their temporal relationships, SAM turns a boxed subject into a moving framing constraint; a bounded Python planner makes a *minimal-change* repair; and — the part it cares most about — the **rendered output is checked** (exact decoded frame count, protected-source inclusion and order, closing interval, subject containment, semantic review) with three visibly different states: **mechanically verified / model-reviewed / human-confirmed**. It rejected Ghost Editor as a roadmap, and warned that PersonCut/Guestlist "can be mistaken for personalized auto-highlights." Its scope: four constraint types only (keep a linked moment pair; use a specified closing moment; hit an exact runtime; keep a selected subject framed), one project, two cameras, no cross-clip identity. Its 90-second beat sheet ends on an impossible brief ("8 seconds, with 12 seconds of locked content") returning a *conflict* instead of silently breaking a promise. Budget ceiling $107 ($50 Spark in, $17 Spark out, $20 SAM, $20 reserve), app-enforced stop at $115. Names: CutPact, SpliceOath, FrameBond, TakeSeal, CutCovenant.

**Where Fable agrees:** Indie. Three features, not a roadmap. The three-state verification idea is excellent and judges will remember it. The "impossible request → conflict" beat is excellent. Analyze once, cache, iterate for free. Freeze code by noon on Nov 4.

**Where Fable disagrees, and the recommendation:** CutPact is an editor's tool; its best moment is a diff. Judges at a Meta/Cerebral Valley final are mostly PMs, researchers and investors, not editors, and the $50k bonus pool includes a community vote and "most viral" — **Guestlist is the one a non-editor explains to a friend in one sentence.** On the rubric: Impact favors Guestlist (guests, venues, parents, schools benefit — not just editors), Tooling favors Guestlist (SAM masks and tracks are the product, not a framing garnish), Demo is a wash in Daniel's hands, Tech favors CutPact, Risk favors CutPact.

So: **build Guestlist, with CutPact's rigor baked in** —
- The headline is the **ledger + consent switch**, never "auto-highlights." Lead the video with the missed guest and the consent flip; the per-person reels are the payoff, not the pitch.
- Adopt the **three verification states**. "This person never appears in the public recap" is *mechanically verified* from SAM masks against the rendered EDL; "this is the same person across two cameras" is *human-confirmed* (Spark proposes); "this moment is meaningful" is *model-reviewed* with a confidence and a review flag.
- Adopt **impossible-request handling**: "exclude the bride from the wedding recap" → *conflict: this person appears in 94% of usable shots* — not a silent, hollow recap.
- Adopt Astra's budget table as the ceiling ($107 planned, hard stop $115) and its Day-9 freeze rule.
- **The pivot is cheap by design.** Days 1–2 build exactly what both ideas need (Files upload, Spark event index with structured output, SAM box/concept tracking, mask decode, GhostCut render + FCPXML). If the Day-3 gate fails on roster/re-ID, switch to CutPact without losing the first two days.

**Final decision is Daniel's** — see §8. If he prefers the lower-risk, higher-engineering-credit route, CutPact is fully specified above and in Astra's round-2 output (kept in the session scratchpad; copy it into `docs/astra-round2.md` of the project repo on Day 1).

Astra cost for this plan: two `gpt-6-astra` calls, 5.4k input + 6.4k output tokens total (incl. 1.5k reasoning).
