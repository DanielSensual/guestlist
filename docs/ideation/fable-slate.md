# Fable slate (Claude Fable 5.1) — 8 ideas

## 1. Ghost Editor — "the editor that actually watches your footage"
Theme: Build for Your World. Track: Startup (it's a product the founder's own company would run on real jobs).
Drop a camera card of raw multi-cam footage. muse-spark-1.3 watches every clip (native video input, 1M context) and writes a structured shot log (scene, who's in frame, action, quality, best 3 seconds, continuity notes). sam-3.1 tracks every person across frames so the editor can answer "every shot with the groom" or "follow dancer #3". muse-voice-transcribe diarizes who said what and syncs cams by audio. Give it a brief ("90s recap, beat-synced to this track, no crew voices") → muse-wonder plans the cut → the open-source ffmpeg pipeline renders it + exports FCPXML for a human finish.
Non-obvious Meta use: SAM tracking as the *selection primitive* (subject-aware search, per-person clips, vertical auto-reframe that follows the tracked subject, privacy blur of non-subjects); Spark video-in as a *logger*, not a chatbot.
Demo moment: "Give me every moment the bride laughs, vertical, captioned" → 40 seconds later, three clips drop, each framed on her.
Risk: too broad. Cut: ship 3 hero features only — shot log + semantic search, SAM subject clips/reframe/blur, brief→cut.

## 2. PersonCut — one clip per guest, delivered
Theme: Build for Your World. Track: Indie or Startup.
Narrow wedge of #1: event footage in → sam-3.1 tracks each person/couple → their own highlight clip rendered and delivered by link/QR. Venues, dance schools, kids' sports, weddings. The founder did exactly this by hand every week for a dance night.
Non-obvious: SAM identity tracking across *clips* (re-ID by appearance), clip stitching per subject, privacy blur of everyone else.
Demo: 30 guests → 30 clips in minutes, each guest's phone buzzes.
Risk: re-ID across clips is hard. Cut: per-clip tracking + human-confirmed grouping UI.

## 3. ListingLens — a home-tour video becomes the whole listing
Theme: Build for Your World (Frontier-adjacent: physical understanding). Track: Startup.
Walkthrough video → Spark names rooms/features, SAM segments fixtures and flags defects (water stains, cracks), outputs: chaptered tour, per-room clips, listing copy, feature sheet, MLS stills, disclosure-flag list with timestamps.
Non-obvious: SAM masks → room-by-room square-footage/material estimates; defect detection as a disclosure aid.
Demo: 4-minute tour → full listing package in 90 seconds.
Risk: measurement claims are shaky. Cut: no measurements; chapters + copy + stills + flags.

## 4. Ghost Dailies — a script supervisor and DIT in a box
Theme: Build for Your World. Track: Indie.
Each night of a shoot, feed the day's footage + the script. Transcribe/diarize matches every take to script lines; Spark grades takes; SAM tracks props/wardrobe across takes to flag continuity breaks; output: coverage gaps vs. shot list, best-take picks, continuity report.
Non-obvious: continuity checking with SAM object tracking; script-line matching from diarized speech.
Demo: "You never got the reverse on line 14, and the glass is in the wrong hand in take 3."
Risk: needs scripted footage; shoot a 2-page scene in the studio.

## 5. Ghost Scout — location walkthrough → shot plan
Theme: Build for Your World. Track: Indie.
Phone video of a location → SAM segments windows/surfaces/light sources, Spark infers light direction and time-of-day, writes a shot list + lighting plan; muse-image generates storyboard frames matched to real frames.
Non-obvious: light-source segmentation → lighting plan; image gen conditioned on real location stills.
Risk: smaller audience; nice but not urgent.

## 6. DroneInspect — drone video → annotated inspection report
Theme: Push the Frontier (understand a physical system). Track: Indie.
Roof/solar/construction drone passes → SAM tracks panels/sections across frames, Spark flags anomalies, outputs an annotated report with timestamps and masks.
Non-obvious: SAM video tracking to build a stitched component map from a moving camera.
Risk: founder doesn't know inspection firsthand; demo credibility. Cut: one asset class (roofs), own drone footage.

## 7. The Agent That Watches — multimodal intake for trades
Theme: Build for Your World (the founder's AI-agency product line). Track: Startup.
Customer texts a video of the leaking AC / cracked tile; Spark diagnoses, SAM isolates the unit/damage, a voice agent calls back with a diagnosis and quote range; job card to the contractor.
Non-obvious: video → spoken diagnosis via diarized two-way call; SAM mask overlay sent back to the customer.
Risk: voice stack integration time. Cut: text/MMS instead of voice.

## 8. MoveMirror — dance technique coach
Theme: Push the Frontier (human motion as a physical system). Track: Indie.
SAM tracks both dancers' bodies; Spark compares to a reference performance and gives timed corrections; overlay render.
Non-obvious: SAM masks as pose proxies without a pose model; music-beat alignment of corrections.
Risk: niche impact; fun demo.

## Fable's bet
#1 scoped to its three hero features, entered as **Startup** if the founder applied Startup (real company, real jobs, deploy on Railway, show a real queue of jobs), else Indie. Memorable because the demo is real footage the judges can see being understood — not a chatbot. #2 and #3 are the fallback wedges if #1 is too wide by day 4.
