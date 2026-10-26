# Day 1 brief — for the Opus 5.5 execution session

Prepared 2026-10-26 by the planning session (Claude Fable 5.1). If you are an execution session reading this: this is your task. Read `HANDOFF.md` and `docs/PLAN.md` §2, §4, §5, §7, §9 and `docs/ideation/astra-round2.md` §2–3 first.

You are executing **Day 1 (Oct 27) of the Guestlist build** in `~/Projects/guestlist` (scaffolded: `README.md`, `HANDOFF.md`, `LICENSE`, `.gitignore`, `docs/`; `git init` done, no commits yet). Do not touch any other repository.

## Deliverables, in order
1. Commit the scaffold (first dated commit), then a Python project skeleton: `pyproject.toml` (package `guestlist`, src layout), a venv (system python is 3.14 — check that GhostCut's `[recap]` extra with opencv/numpy installs on it; if not, make a 3.12 venv with `uv` or `pyenv` if present and note it in HANDOFF), dependencies: `openai` SDK, GhostCut as an editable path dependency (`~/Projects/Websites/Bots/ghostai-video-editor`), `numpy`.
2. `src/guestlist/meta/`: `client.py` (key from env; `~/.config/ghostai/meta-api.env` provides `MODEL_API_KEY` — never copy the key into the repo), `files.py` (upload with `purpose=user_data` and `expires_after` 7 days; delete helper), `sam.py` (concept + box/point prompt builder, streaming parser for the per-frame `<Nf>id<|box;...|><|mask;...|>` grammar, RLE mask decode for one frame to verify — docs: `https://dev.meta.ai/docs/sam/segmenting.md`, `.../sam/reading-segmentation.md`, `.../sam/client-libraries.md`, plain markdown, curl them), `spark.py` (video-in structured-output call returning `events[]` with `t_start, t_end, people, what, why_it_matters, score, confidence`). **Every API response is cached on disk** under `.cache/` keyed by (file sha256, model, prompt hash) so re-runs are free.
3. `scripts/spike_day1.py` on the dev clip (a private 4K dance clip passed with `--clip`; development only, never demo footage): cut a 60 s 720p 12 fps faststart proxy with ffmpeg; upload it; run SAM concept `person`; run one box-prompt re-track of one object from a mid-clip frame with `propagation_direction: forward`; run the Spark 1.3 video log with structured output; optionally one Voice Transcribe DIARIZATION call on the proxy's audio. **Measure and write down:** Spark input tokens per second of video (the unknown the whole budget depends on), SAM frames billed and wall-clock latency, whether a 60 s clip is accepted in one request and what the max looks like, upload size behaviour, and the dollar cost of every call from the usage fields and `x-ratelimit-*` headers.
4. Save the real API responses as fixtures under `tests/fixtures/` and write tests for the SAM parser, RLE decode and the Spark JSON schema that run with no network.
5. Update `HANDOFF.md`: status, the measurements, the spend ledger, a go/no-go against `docs/PLAN.md` §7 (if Spark video tokens make the $107 ceiling impossible, propose the proxy fps/resolution that fits), and the exact next step for Day 2. Commit as you go with clear messages; the dated history is part of the submission.

## Rules
- Spend no more than **$10** on Day 1. Before any single call that could exceed $2, stop and report instead of running it.
- Proxies only — never upload camera originals. Set `expires_after` on every upload and delete spike uploads when done.
- Never use `muse-spark-1.3-contributor` or any `-contributor` model. `max_output_tokens >= 4000`, `stream: true` for video calls. Use a `developer` message, not `system`.
- Do not create the GitHub repo or push yet: finish with a one-line ask to Daniel to confirm the repo name `guestlist` (check `gh repo view DanielSensual/guestlist` for a collision first and report it).
- This Mac has 16 GB RAM: no browsers or dev servers alongside ffmpeg renders. Verify with tests and curl.
- If SAM or Spark calls fail in ways the docs don't explain, capture the exact request/response in HANDOFF.md and move on to what works — the report is the deliverable.

## Done looks like
A committed skeleton with working `meta/` clients and cached responses, passing offline tests, a 60 s proxy that went through SAM (concept + box re-track) and Spark end to end, and a `HANDOFF.md` that states the measured tokens/sec, frames/latency, dollars spent, go/no-go on the budget, and the Day-2 step. End with a short report of those numbers.
