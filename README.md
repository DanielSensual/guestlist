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
