# Hallucination Watch — Algorithm Specification

## Overview

Low-cost hallucination risk screening via behavioral proxy signals. Two phases: Baseline (record only) and Active (full detection).

## Phase Design

### Phase 1: Baseline
Variable N (min 6, max 20), data-driven. Collects formula_raw for calibration.

### Dynamic N
Baseline extends automatically when CV > 0.3.

### Calibration
threshold = max(mean + 3.0 × std, 100)

### Phase 2: Active
Full detection with calibrated threshold.

## Topic Tracking
Zero-dependency Jaccard similarity on content words.

## Three-Zone Decision
Green (<100%): Silent | Yellow (100-200%): Mark | Red (≥200%): Verify

## Density Normalization
Density-normalized subjective count prevents false positives on long-form content.

## Reference Material Anchoring
Stores claims during sustained research/writing. Checks for self-contradiction.

## Character Extraction
Hash-based deterministic + habit-profile weighted.

## Fuzzy Matching
difflib.SequenceMatcher with hybrid scoring: max(50, (100-sim)×2.5)

## Decision Formula
trigger_score = density_subjective + fuzzy + redundancy + material_inconsistency

## Self-Adaptation Layer
EMA + trigger rate feedback. Runs every 10 conversations.

## Self-Correction Layer
Direction B (internal) + Direction A (claim Web Fetch). Dynamic selection mechanism.

## User Feedback Channel
User corrections are informational, not algorithmic. Records user_contested without affecting adaptation.

Full spec: See SKILL.md and scripts/ for implementation details.