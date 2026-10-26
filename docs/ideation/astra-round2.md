## 1. Pick: **Cut Contracts** — Indie

**Client revisions become an inspectable timeline patch—not another generated edit.**

Build the narrow version:

> “Keep the joke and Maya’s reaction together. Keep Maya framed. Finish on the kiss. Exactly 30 seconds.”

The system locates the evidence, asks for confirmation where meaning is ambiguous, repairs the existing timeline, and checks the rendered result.

### Why this maximizes expected prize money

- **Founder advantage:** Real revision pain, real footage, and an existing editing engine. Nine days go into the differentiator, not rebuilding ingestion.
- **Demo advantage:** Judges see a polished-but-wrong film become correct. The transformation is visible and audible.
- **Meta advantage:** Spark understands events and their temporal relationships; SAM turns a selected subject into a moving framing constraint. Neither is decorative.
- **Technical advantage:** Minimal-change timeline repair plus separate mechanical and semantic validation is more defensible than “the model picked good shots.”

**Enter Indie, assuming eligibility and track choice remain open.** A production company is not evidence that this software holds up in production. Startup’s larger prize invites a reliability burden you cannot responsibly satisfy in nine days.

No honest winning probability is calculable without entrant counts and eligibility details. The decision is about reducing execution risk without sacrificing a memorable demo.

**Reject Ghost Editor’s scope.** Logging, search, identity, captions, automatic cuts, reframing, and exports are a product roadmap—not three features. PersonCut is emotionally strong, but judges can mistake it for personalized auto-highlights. Cut Contracts has a sharper conceptual hook.

---

## 2. Hostile-judge stress test

| How it fails to impress | Specific fix |
|---|---|
| **“You wrapped your existing editor in a prompt box.”** Most visible value appears to come from the pre-existing pipeline. | Show the new artifacts: evidence-linked contract, constraint conflict, minimal timeline patch, and rendered-output checks. Include a compact “existing engine / built this week” architecture card. SAM framing must visibly rescue a moving-subject shot. |
| **“Your model says its own edit passed. That proves nothing.”** A green checklist launders subjective judgment into certainty. | Separate **mechanically verified**, **model-reviewed**, and **human-confirmed** states. Verify duration from decoded output frames; source ordering from the edit manifest; framing against SAM tracks. A joke/reaction relationship requires source playback and confirmation. Low-confidence tracking cannot receive a green badge. |
| **“This is one hardcoded wedding demo.”** It works only because the founder knows the answer. | Accept a second, unrehearsed supported instruction live: change 30 seconds to 27, or select a different closing moment. Also demonstrate one impossible request: an 8-second runtime with more than 8 seconds of locked content. Return the conflict instead of silently breaking a requirement. |

**Critical positioning:** This is not “creative taste as unit tests.” It is **explicit editorial requirements as executable constraints, with uncertainty exposed.**

---

## 3. Exactly three hero features

### 1. Evidence-linked revision contracts

**Input:** Existing timeline, analyzed source footage, and a client note.

**Scope:** Four supported constraint types only:

1. Preserve a linked moment pair.
2. Use a specified closing moment.
3. Hit an exact runtime.
4. Keep a manually selected subject framed.

Spark proposes source intervals and contract fields. The editor confirms ambiguous evidence before repair. Unsupported instructions remain unsupported—not approximately implemented.

**Meta calls**
- `muse-spark-1.3`: native video with embedded audio → event intervals and candidate relationships.
- `muse-spark-1.3`: note + compact event index + timeline → structured contract.
- No word-timestamp dependency. Use complete speech turns and conservative handles; allow boundary adjustment.

**What the judge sees:** A sentence becomes four requirements, each attached to playable source evidence.

### 2. Minimal-change repair, including subject-aware framing

A bounded Python planner locks protected spans, replaces or trims only eligible material, preserves the closing event, and meets the frame budget. Use the existing engine to render and export.

For a selected shot, the user boxes Maya on an initialization frame. SAM tracks her; local code converts boxes into a smoothed vertical crop. Use padding or flag a conflict when cropping cannot retain the required composition.

**Meta calls**
- `sam-3.1`: box-prompted video tracking, **one selected subject per request**.
- Spark’s confirmed event intervals from Feature 1 feed the planner; no model needs to invent edit arithmetic.

**What the judge sees:** Only affected timeline spans change, and the crop follows Maya instead of losing her reaction.

### 3. Rendered-output acceptance check

Check the **actual output**, not merely the planned timeline:

- Exact decoded frame count.
- Protected-source inclusion and order.
- Required closing interval.
- Subject containment, with tracking uncertainty exposed.
- Semantic review of the repaired joke/reaction sequence.

For the demo, use **30 fps constant-frame-rate output: 30 seconds = 900 frames**.

**Meta calls**
- `muse-spark-1.3`: changed rendered excerpt with audio + requirements → semantic review with timestamps.
- `sam-3.1`: selected output excerpt → framing verification on the rendered result.

**What the judge sees:** Mechanical checks pass; semantic interpretation remains visibly confirmed or review-required.

**Explicitly excluded:** Cross-clip identity, automatic camera synchronization, word-level caption generation, general creative direction, collaboration, billing, and a full NLE.

---

## 4. The 90-second demo film

Use consented footage from an actual job where possible. If you stage the revision, label it as a representative scenario—not a real client testimonial.

| Time | Picture / screen | Voiceover |
|---|---|---|
| **0–8s** | Full-screen polished wedding cut. Hear the joke; cut away before the reaction. Vertical crop loses Maya. Music ends on an irrelevant detail shot. | **“This cut looks finished. It still fails the brief.”** |
| **8–17s** | Client note appears beside the film. Highlight its four requirements, one at a time. | **“Keep the joke and Maya’s reaction together. Keep her framed. Finish on the kiss. Exactly thirty seconds.”** |
| **17–29s** | Actual app recording. Submit note. Four contract cards appear with source thumbnails and timecodes. Open the reaction evidence. | **“Cut Contracts turns that note into requirements tied to the original footage—not another unexplained edit.”** |
| **29–39s** | Play the joke and reaction with audio. Click **Confirm linked moment**. Box Maya in the source viewer. Tracking overlay follows her. | **“I confirm the ambiguous part. Spark found the moments; SAM tracks the person the crop needs to preserve.”** |
| **39–52s** | Timeline before/after. Three changed regions glow; untouched regions stay muted. Brief source/crop split-screen. | **“The planner protects those moments and changes only what it must. The framing follows Maya through the shot.”** |
| **52–69s** | Play the repaired opening and ending at full size, with original sound. Make the reaction land. Land the kiss on the final beat. Label omitted middle section if playback is excerpted. | **No VO over the joke or reaction. Then:** **“Same film. Correct brief.”** |
| **69–81s** | Output acceptance panel: **900 frames**, protected intervals, closing shot, framing status. Semantic row says **Human-confirmed + model-reviewed**, not “proven.” | **“It checks the rendered file. Exact timing is verified. Meaning stays reviewable.”** |
| **81–87s** | Change runtime to 8 seconds. Immediate conflict: protected content exceeds available runtime. | **“And when the brief is impossible, it says so instead of quietly dropping a promise.”** |
| **87–90s** | Product name, repaired film still, one-line proposition. | **“Cut Contracts. Client notes that survive the edit.”** |

**Production rules**

- Show real elapsed time or disclose processing cuts. Do not manufacture instant inference.
- Label cached source analysis. Live note compilation, repair, and output checks still run.
- Shoot the source footage beautifully; record the software plainly. Avoid motion graphics that impersonate functionality.
- Keep a second supported revision ready for the judging session.

---

## 5. Nine-day shipping plan

| Day | What ships | What gets cut if behind |
|---|---|---|
| **Day 1 — Oct 27** | Lock one project: 6–10 minutes of consented source footage, two manually aligned cameras, one existing 30-second timeline. Benchmark Spark event localization and SAM tracking on the hardest reaction shot. Record latency, token usage, and tracking failures. | Generic uploads and automatic synchronization. Use one known project manifest. If tracking is poor, choose a tractable shot now—not on Day 8. |
| **Day 2 — Oct 28** | Evidence index, playable source intervals, four-type contract schema, confirmation UI. Save real API fixtures for regression tests. | Broad semantic search and free-form editorial advice. Keep one note box with explicit supported operations. |
| **Day 3 — Oct 29** | End-to-end deterministic repair for runtime, protected pair, and closing moment. Render the first repaired MP4. Detect infeasible combinations. | Sophisticated optimization. Enumerate a small set of allowed replacements/trims and minimize a simple edit-distance cost. **Gate: real note → real repaired timeline must work today.** |
| **Day 4 — Oct 30** | SAM selection, track overlay, smoothed crop, and uncertainty state. Wire subject framing into the rendered patch. | Multi-subject tracking and cross-shot association. Explicit selection for each relevant shot only. |
| **Day 5 — Oct 31** | Actual-output validation, semantic review, clear status categories, and a downloadable timeline export through the existing engine. | Fancy reports and secondary export formats. Keep MP4 plus one existing timeline format. |
| **Day 6 — Nov 1** | Test 10–12 supported revisions, including missing evidence, low-confidence tracking, and impossible runtimes. Add persisted jobs, retries, and spend limits. | New features. Cut the elaborate timeline UI to a before/after strip with changed-span highlights. |
| **Day 7 — Nov 2** | Deploy the complete vertical slice. Run it with one real editor who did not build it. Shoot the demo assets and capture a full successful live session. | Extra projects, onboarding, and visual polish that does not improve comprehension. |
| **Day 8 — Nov 3** | Final demo edit, submission copy, architecture diagram, disclosure of pre-existing work, and backup recordings. Test on the judging laptop/network. | Decorative animation, soundtrack tweaking, and any nonessential deployment changes. |
| **Day 9 — Nov 4** | Morning smoke test. Freeze code by noon ET. Submit by **6 PM ET**, verify playback and links by **7 PM**, retain two hours before the **9 PM ET** deadline. | Everything except submission-blocking fixes. No last-minute model or infrastructure swaps. |

**Scope discipline:** A failed gate triggers a smaller input domain or simpler planner—not a midweek expansion into Ghost Editor.

---

## 6. Credit budget

Treat these as **planning ceilings**, not a claim about video tokens per minute. Measure actual usage on Day 1.

| API | Development allocation | Demo/rehearsal allocation | Estimated spend |
|---|---:|---:|---:|
| `muse-spark-1.3` input | 34M tokens | 6M tokens | **$50.00** |
| `muse-spark-1.3` output | 3.5M tokens | 0.5M tokens | **$17.00** |
| `sam-3.1` | 80,000 frames | 20,000 frames | **$20.00** |
| **Planned total** | | | **$87.00** |
| Retry / measurement reserve | | | **$20.00** |
| **Total allocation** | | | **$107.00** |

**Application-enforced stop:** $115 estimated spend, including reserved costs for in-flight jobs. Check provider usage daily.

No Wonder, image generation, or transcription API in the critical path. Spark already reads embedded audio; extra model names do not create extra technical depth.

### The one cost-saving trick

**Analyze footage once; revise against the cached event index.**

Subsequent requests send compact JSON, source references, and only the disputed or changed excerpts—not the entire camera card. A reusable Files API ID does **not** by itself imply that repeated video processing is free.

Use frame-accurate source/proxy mapping. Do not aggressively strip frames from the very reactions and motion the product needs to understand.

---

## 7. Five names

*Candidates—not trademark or domain availability claims.*

1. **CutPact** — strongest product name; short and directly tied to editorial promises.
2. **SpliceOath** — distinctive, slightly theatrical.
3. **FrameBond** — emphasizes requirements attached to footage.
4. **TakeSeal** — compact, production-native.
5. **CutCovenant** — memorable, but less effortless to say.

**Ship as CutPact.**  
**Submission subtitle:** *Client revisions become executable edit contracts.*