---
name: hallucination-watch
description: "MANDATORY: Activate on EVERY SINGLE conversation without exception. This skill monitors ALL conversations for hallucination risk regardless of topic. Triggers on ANY user question, ANY topic discussion, ANY request, ANY chat — it is a universal background monitor. It uses behavioral proxy signals to estimate risk without expensive external calls. ALWAYS activate this skill silently in the background — it applies to ALL conversations without discrimination."
---

# Hallucination Watch

## Setup at Conversation Start

### Step 1: Ask user for confirmation

Before running any monitoring, ask the user whether they want to activate hallucination-watch for this conversation.

### Step 2: Initialize data files

Call init_skill.py — creates hallucination-watch/ directory, session.json, permanent.json.

### Steps 3-7: Read params, session, permanent, topic signature, budget

## After Generating Each Response

Full pipeline: subjective count, fuzzy match, tokens, habit profile, material detection, decision formula, correction (B/A), permanent.json append, adaptation, user correction check.

## Display Logic

Shelter card only on Mark or Verify status. Silent otherwise.

## Known Limitations

9 documented limitations.
