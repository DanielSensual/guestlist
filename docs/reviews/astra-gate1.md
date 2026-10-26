# Astra gate review #1 (GPT-6 Astra, 2026-10-26, end of build Day 3)

Input: docs/PLAN.md §1–2, HANDOFF.md, docs/day3-roster.json (trimmed), windows.py, roster.py, moments.py, Spark prompts.
What was acted on is listed in HANDOFF.md under "Astra gate review #1".


## 1. Verdict: **continue, with narrower scope and a Day-4 gate**

**The Day-3 gate was not passed.** It required real demo footage; none exists. “Tracking + roster hold on the worst footage” is unsupported: two foreground dancers survive, but 212 tracks become 204 identities, and the roster remains unreviewed.

Scope: **editor-assisted guest reels for small, consenting events**, not “knows who is in every frame.” Keep human-confirmed identity, coverage accounting, and exclusion by shot removal. Defer automatic privacy-safe blur, SFace, voice, and title-card work.

**By end of Day 4:** shoot two synchronized, three-minute camera clips; freeze settings before evaluating a held-out take. Proposed gate:
- All 5–6 guests correctly grouped after ≤10 minutes of review.
- ≥95% tracking recall on manually annotated, clearly visible person instances sampled each second.
- No unresolved identity switches in selected reel intervals, checked continuously.
- One playable per-person reel with correct source timecodes.

Fail—or still no footage—and pivot. I don’t know CutPact’s implementation readiness; don’t assume pivoting is free.

## 2. Claims that do not hold

- **“Known-answer eval”: `roster.eval_cases`.** SAM supplies both the positives and negatives. Split tracks can contain identity switches; simultaneous tracks can duplicate one person or represent reflections. Inspect and manually label every case before calling it ground truth.
- **Threshold calibration is contaminated.** Crop changes and thresholds were selected on these same 29 cases. Same-track halves also underrepresent cross-camera viewpoint changes and re-entry. Hold out a separate take; shuffle gallery positions; include absent identities and similar outfits.
- **“Only top confidence is informative.”** At ≥0.9, truth-present results contain **9 correct and 1 wrong accepted match**: 90% observed precision, 31% recall. Zero false matches among 29 negatives does not establish safety; even assuming independent cases, the one-sided 95% upper bound is roughly 10%. Confidence is not calibrated probability.
- **“76 supported moments.”** This means temporal presence, not correct action, identity, or editorial quality. Rename it `presence_supported`. Follow-crops may help attribution; they do not validate it.
- **“0.17 s first-seen error.”** This measures agreement with burned-in SAM tags, not independent person detection. The decoy tests unused-label restraint, not identity accuracy.
- **“$8.40 demo.”** Forty minutes at 12 fps costs $5.76 for one SAM pass; observed crowded-window overhead of 2.2× makes that approximately **$12.67 before further re-tracks**. Per-guest Spark calls also invalidate a simple per-footage-hour extrapolation.
- **“No embeddings keeps it legal in BIPA states.”** Delete this legal conclusion. Transient processing is not automatically exempt; no stored database is not a compliance determination.

## 3. Code risks

- **`windows.py::stitch`:** one shared frame can authorize an irreversible merge. Greedy box-IoU matching is vulnerable when couples overlap; earlier-window masks win regardless of quality. Require minimum overlap support and an ambiguity margin; retain uncertain seams for review.
- **`windows.py::cut_window`:** `dst.exists()` can reuse stale footage after source replacement. Key artifacts by source hash and processing parameters. `plan_windows` also needs validation: overlap ≥ window can prevent progress.
- **`roster.py::flag_conflicts`, `Roster.decide`, `accept_suggested`:** checks cover shared targets, not shared queries or transitive component conflicts. `decide` permits accepting an already rule-rejected conflict; bulk acceptance bypasses `decide`. Enforce component-level cannot-link constraints on every acceptance path.
- **`roster.py::Roster.people`:** labels renumber after merges; `confirmed=any(...)` silently extends confirmation to newly attached tracks. Names can conflict silently. Use stable person IDs, version derived moments, and invalidate confirmation after membership changes.
- **`roster.py::Roster.people`:** summed track seconds double-count overlapping fragments and synchronized cameras. Distinguish camera-seconds from unioned event-time coverage.
- **`moments.py::check_event`:** `unmarked` alone becomes overall `supported`; timestamps lack finite-value and clip-bound checks. A one-second appearance can support an arbitrarily long event. Validate bounds and separate subject coverage from incidental co-presence.

## 4. Days 4–6: ranked by judging impact/hour

1. **Shoot and adjudicate the gate — Day 4, 3–4 hours.** Highest leverage across every category. Record review time and errors.
2. **Deliver ledger → reel — Day 4–5, 4–6 hours.** Seed an expected guest roster manually: tracking cannot enumerate people it never detected. Separate “not detected,” “unreviewed,” and “excluded from recap.”
3. **Expose Meta’s actual contribution — Day 5, 2–3 hours.** Show SAM masks/tags feeding Spark’s structured proposal, then source-linked verification. This—not API count—is the unexpected capability.
4. **Make roster decisions reversible and consistent — Day 5, 3–4 hours.** Fix conflicts, stable IDs, confirmation invalidation; add regression tests.
5. **Build fail-closed exclusion — Day 6, 4–6 hours.** Remove affected shots, invalidate served outputs, block uncertain exports. Audit final-resolution, full-frame-rate renders. Defer blur.

## 5. Three-minute demo: three moments

1. **0:00–0:45:** two camera tracks → one confirmed guest; show an ambiguous merge being rejected. This builds on existing functionality.
2. **0:45–1:45:** “missing from recap” → exact overlooked source moment → playable guest reel. Explicitly distinguish omission from detection failure.
3. **1:45–3:00:** exclude guest → old deliverable unavailable → replacement recap; unresolved overlap blocks publication.

The latter two are **build targets, not demonstrated capabilities today**. Label cached analysis honestly.

## 6. Shoot honestly

Use soft lighting, locked exposure, ordinary distinguishable outfits, and a synchronization clap. Include one similar-outfit pair, exit/re-entry, partner overlap, back-facing turn, dim passage, and genuine background-only moment. Give the second camera useful alternate coverage.

Reserve an untuned take. Keep failures visible in review. Six friends cannot test crowd saturation: disclose that limitation separately using authorized club evidence. Stage withdrawal only with actual continuing permission to show the demonstration.