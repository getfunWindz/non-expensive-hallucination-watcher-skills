---
name: hallucination-watch
description: "Background conversation risk monitor — activates automatically on every conversation. Screens all user messages for hallucination risk using behavioral proxy signals (subjective language, cross-session consistency). Triggers naturally on questions, discussions, requests, code, writing, or any interaction. Silent background operation, only surfaces alerts when risk is detected. A natural companion for any conversation that benefits from content quality awareness."
---

# Hallucination Watch

Low-cost hallucination risk screening. Runs silently in the background, alerts only when needed.

## Setup (Auto-Run)

Run these steps at conversation start. No user interaction needed.

### Step 1: Initialize data files
### Step 2: Load config
### Step 3: Load session state (session.json, permanent.json)
### Step 4: Extract topic signature from user message

## Per-Response Pipeline

1. Count subjective keywords (density-normalized)
2. Extract chars + fuzzy score (topic-filtered)
3. Count tokens via tiktoken
4. Run decision formula (three-zone: Safe/Mark/Verify)
5. Write session.json
6. Check & store reference material
7. Append to permanent.json
8. Run adaptation (every 10 conversations)
9. Run correction (Direction B internal / Direction A Web Fetch)
10. Check for user correction signals

## Display

Shelter card only on Mark or Verify. Silent otherwise.

## Known Limitations

9 documented limitations.
