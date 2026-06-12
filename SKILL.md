---
name: hallucination-watch
description: "Background conversation risk monitor — activates automatically on every conversation. Screens all user messages for hallucination risk using behavioral proxy signals (subjective language, cross-session consistency). Triggers naturally on questions, discussions, requests, code, writing, or any interaction. Silent background operation, only surfaces alerts when risk is detected. A natural companion for any conversation that benefits from content quality awareness."
---

# Hallucination Watch

Low-cost hallucination risk screening.

## Setup (Auto-Run)

Run at conversation start. No user interaction needed.

1. **Initialize**: run init_skill.py
2. **Load config**: read params/default.json
3. **Load state**: read session.json + permanent.json
4. **Extract topic**: run topic_embed.py on user message

## Per-Response Pipeline

1. **Count subjective keywords** — density-normalized (count / tokens x 1000)
2. **Extract chars + fuzzy score** — hash-based, topic-filtered
3. **Count tokens** — recount ALL messages (tiktoken). Track cumulative_total. Redundancy uses conversation turns (every 10 turns = +10).
4. **Run decision formula** — density_subj + fuzzy + redundancy + material_penalty; three-zone: less than 100% silent, 100-200% Mark, at least 200% Verify
5. **Write session.json** — include cumulative_total
6. **Reference material** — store if collecting, check consistency
7. **Append permanent.json**
8. **Adaptation** — run adapt_threshold.py every 10 conversations
9. **Correction** — Direction B (internal) / Direction A (claim Web Fetch)
10. **User correction check** — record user_contested, force verify, do NOT use for adaptation

## Display

Shelter card only on Mark or Verify. Silent otherwise.

## Known Limitations

10 documented (incl. redundancy uses turns, not tokens).
