---
name: hallucination-watch
description: "Background conversation risk monitor — activates automatically on every conversation. Screens all user messages for hallucination risk using behavioral proxy signals (subjective language, cross-session consistency). Triggers naturally on questions, discussions, requests, code, writing, or any interaction. Silent background operation, only surfaces alerts when risk is detected. A natural companion for any conversation that benefits from content quality awareness."
---

# Hallucination Watch

Low-cost hallucination risk screening.

## Setup (Auto-Run)

### Step 1: Initialize data files via init_skill.py
### Step 2: Load config (params/default.json)
### Step 3: Load session state (session.json + permanent.json)
### Step 3b: Determine phase + calibrate threshold via calibrate_threshold.py at baseline->active transition
### Step 4: Extract topic signature via topic_embed.py

## Per-Response Pipeline

1. Count subjective keywords (density-normalized)
2. Extract chars via fuzzy_match.py / calc_habit.py; compute fuzzy score
3. Count tokens: complexity_estimator.py estimates thinking, count_tokens.py sums visible + thinking, redundancy = cumulative / tpi * increment
4. Decision formula: density_subj + fuzzy + redundancy + material_penalty; three-zone
5. Write session.json
6. Reference material: reference_material.py add/check
7. Append permanent.json
8. Adaptation: adapt_threshold.py (threshold + redundancy scaling)
9. Correction: correction.py (Direction B internal + Direction A claim Web Fetch)
10. User correction check

## Display

Shelter card only on Mark or Verify. Silent otherwise.

## Known Limitations

10 documented.