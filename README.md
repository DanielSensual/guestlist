# Guestlist

**The event-footage system that knows who is in every frame. Every guest gets their own film. Anyone can opt out.**

Built for the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026) on the Meta Model API:
SAM 3.1 tracks every person through every clip, Muse Spark picks each person's moments and proposes
roster matches for a human to confirm, and a consent switch re-cuts the public recap around anyone
who opts out — with a review queue for the frames the model isn't sure about.

**Disclosure.** Rendering, beat-sync recap cutting, proxies, captions and FCPXML/OTIO export come from
[GhostCut](https://github.com/DanielSensual/ghostcut), the author's open-source (MIT) pipeline, public
since July 2026. Everything in `src/guestlist/` — the SAM tracker, roster, moments, ledger, consent
engine and the web app — is new work for this hackathon, with dated commits.

See `docs/PLAN.md` for the build plan and `HANDOFF.md` for current status.

## How it works (built so far)

| Step | Meta model | What we found and did |
|---|---|---|
| Track everyone | SAM 3.1 (video, concept prompt `person`) | One request hands out at most **16 object ids**, so a crowded room fills up in seconds. `windows.py` runs overlapping 10 s windows, splits any that come back full, and stitches ids by box overlap: 111 tracks instead of 16 on a 60 s club clip. |
| Tag the video | — | `burn.py` draws each track's outline and `#tag` into a copy of the proxy. |
| Name people by our tags | Muse Spark 1.3 (video in, strict JSON schema with an `enum` of our tags) | Spark's log refers to people by the tracker's tags instead of its own labels; its first-seen times match SAM's to a median 0.17 s and a decoy tag drawn on nobody was never used (agreement with our own tags, not an identity check). |
| Check every claim | — | `moments.py` tests each Spark moment against SAM's frames: a *presence* check (was that tag on screen then?), not proof the action is theirs. |
| Group tracks into people | Muse Spark 1.3 (image in) | Geometry proposes which fragments could be one person; Spark picks from a lettered comparison sheet. On 29 test cases derived from SAM tracks (not yet hand-labelled), its picks at confidence ≥ 0.9 were right 9 times in 10; below that it guesses. Only ≥ 0.9 is pre-selected, conflicts are resolved by rule, and a human confirms every merge (`app/`, FastAPI + HTMX). |
| Per-person moments | Muse Spark 1.3 (video in) | Each guest's own moments from the tagged clip, presence-checked against their frames. |

## Run it

```bash
uv venv --python 3.13 .venv && source .venv/bin/activate
uv pip install -e ".[test]" -e /path/to/ghostcut
(cd tools/sam-decode && npm ci)
python -m pytest
MODEL_API_KEY=... python scripts/day3_roster.py prepare within across moments   # needs your own footage
python -m guestlist.app --project projects/dev                                   # roster review on :7788
```
