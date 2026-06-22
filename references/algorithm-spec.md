# Hallucination Watch — Algorithm Specification

## Overview

This algorithm estimates hallucination probability in LLM conversations using three proxy signals and a decision formula. It operates in two phases: **Baseline** (record only, no action) and **Active** (full detection + optional Web Fetch verification).

---

## Phase Design

### Phase 1: Baseline (Conversations 1 ~ N)

| Setting | Value |
|---------|-------|
| Duration | Variable N (min: 6, max: 20), data-driven |
| Behavior | All counters run, formula_raw recorded in turns.json |
| Web Fetch | NEVER triggered (threshold is infinite during this phase) |
| Purpose | Build habit_profile, collect formula_raw for calibration |

### Dynamic N (Variance-Based Extension)

Baseline N is no longer a fixed constant. It extends automatically when the model's behavior is still settling.

**Decision logic:**

```
n = current baseline record count

if n < min_baseline_n (6):
    → stay in baseline (minimum not met)

if n >= min_baseline_n AND n < max_baseline_n (20):
    compute cv = std / mean  (coefficient of variation)
    if cv <= variance_stable_threshold (0.3):
        → calibrate and transition to active
    else:
        → extend baseline (behavior still fluctuating)

if n >= max_baseline_n (20):
    → force calibrate regardless of stability
```

**Rationale:** A model that gives very different formula_raw values in its first 6 conversations hasn't settled into a predictable pattern yet. Waiting for stability prevents a bad initial threshold.

### Calibration (Transition)

At the baseline → active transition, `calibrate_threshold.py` reads all baseline formula_raw values and computes:

```
threshold = max(mean + multiplier × std, min_threshold)
```

| Parameter | Default | Effect |
|-----------|---------|--------|
| `multiplier` | 3.0 | Higher = more conservative (fewer triggers) |
| `min_threshold` | 100 | Floor to avoid triggering on noise |

Example outcomes by model personality:
- **Cautious model** (baseline raw ~40, std ~10): threshold = max(40+30, 100) = 100
- **Confident model** (baseline raw ~200, std ~40): threshold = max(200+120, 100) = 320
- **Variable model** (baseline raw ~150, std ~80): cv = 0.53 > 0.3 → extend baseline

### Phase 2: Active (Conversation N+1 onwards)

| Setting | Value |
|---------|-------|
| Behavior | Full detection with calibrated threshold + habit_profile-weighted extraction |
| Web Fetch | Triggered if formula result >= auto_verify threshold |

---

## Topic Tracking (Zero-Dependency)

File: `scripts/topic_embed.py`

Cross-session fuzzy comparison only produces meaningful signals when both conversations are about the same topic. Topic tracking filters out cross-topic comparisons.

### Approach: Jaccard Similarity on Content Words

```python
def extract_topic_sig(text):
    """Extract content words/tokens as topic signature."""
    ascii_words = re.findall(r'[a-zA-Z]+', text.lower())
    cjk_chars = re.findall(r'[\u4e00-\u9fff]', text)
    all_tokens = [w for w in ascii_words if len(w) > 1] + cjk_chars
    # Remove stop words, return top 10 tokens
    return dict(Counter(t for t in all_tokens if t not in STOP_WORDS).most_common(10))

def topic_similarity(sig_a, sig_b):
    """Jaccard similarity between two topic signatures."""
    set_a, set_b = set(sig_a.keys()), set(sig_b.keys())
    return len(set_a & set_b) / len(set_a | set_b) if set_a and set_b else 0.0
```

### Decision

| Topic Similarity | Behavior |
|-----------------|----------|
| ≥ threshold (default 0.15) | Same topic → normal fuzzy comparison |
| < threshold | Different topic → fuzzy_score = 0, record `topic_drift = true` |

### Cost

Zero external dependencies. Pure Python stdlib. ~1ms per operation.

---

## Three-Zone Decision

The original binary trigger (trigger / no-trigger) is replaced with three zones, giving users control over verification cost.

| Zone | Condition | Status | Behavior | Cost |
|------|-----------|--------|----------|------|
| **Green** | score < 100% | Safe / Watch | Metrics only | 0 |
| **Yellow** | 100% ≤ score < 200% | Mark | Highlight claims, prompt user to verify | 0 (unless user opts in) |
| **Red** | score ≥ 200% | Verify | Auto Web Fetch + correction | 1-3 fetches |

### Configuration

```json
{
  "auto_verify_multiplier": 2.0
}
```

The multiplier determines where the Yellow→Red boundary lies:
- `1.5` → Red zone starts at 150% (more aggressive)
- `2.0` → Red zone starts at 200% (default, moderate)
- `3.0` → Red zone starts at 300% (conservative, saves budget)

### Monthly Budget

```json
{
  "web_fetch_monthly_budget": 200,
  "budget_reset_day": 1
}
```

When the monthly budget is exhausted, Red zone triggers are demoted to Yellow (Mark + prompt). This guarantees cost is bounded.

---

## Density Normalization

### Problem

In long-form content (novels, papers, technical documentation), the absolute count of subjective keywords scales with text length. A 10,000-token chapter naturally contains more "absolutely." statements than a 200-token Q&A, even at the same density. Without normalization, long content triggers false positives.

### Solution

Subjective count is normalized by response token count:

```python
density_subjective = (subjective_count / max(response_tokens, 1)) × density_multiplier
```

| Scenario | Old Score | New Density Score | Correct Behavior |
|----------|-----------|-------------------|------------------|
| Short Q&A (200 tok, 3 subj) | 3 | 15 | baseline unchanged |
| Novel chapter (8K tok, 60 subj) | **60 (false positive)** | **7.5 (correct)** | false positive eliminated |

### Parameter

```json
{ "density_multiplier": 1000 }
```

The multiplier maps density to the same scale as other signals (fuzzy_score 0-250). A density of 0.015 words/token → 15 on display scale.

---

## Reference Material Anchoring

### Motivation

During long-form research or writing, users collect facts from model responses. If the model later contradicts its own previously provided facts, this is a hallucination signal. Reference material anchoring stores key claims during "collection mode" and checks subsequent responses for consistency.

### Collection Mode Detection

The skill enters collection mode after 3+ consecutive same-topic conversations (no topic drift). This indicates the user is engaged in sustained research or writing.

### Storage

File: `hallucination-watch/sessions/{session_id}/reference.json`

```json
{
  "last_updated": "2026-06-07T16:00:00Z",
  "entries": [
    {
      "topic_sig": {"法":1,"国":1,"首":1,"都":1},
      "claims_text": "法国的首都是巴黎…",
      "timestamp": "2026-06-07T15:30:00Z"
    }
  ]
}
```

### Consistency Check

On every response, the skill checks whether the current topic overlaps with any stored material entry using Jaccard similarity:

```python
def topic_overlap(sig_a, sig_b):
    set_a, set_b = set(sig_a.keys()), set(sig_b.keys())
    return len(set_a & set_b) / len(set_a | set_b)
```

If overlap ≥ `material_collection_threshold` (0.15), a consistency score is computed:

```python
matches = count(material_entries where overlap >= threshold)
material_inconsistency = max(0, 40 - matches * 8)
```

This penalty is added to the trigger score.

### Limitations

- **Topic-gated**: Only activates after 3 consecutive same-topic conversations.
- **Self-referential**: Stored claims come from model responses, not external verification. The system detects **self-contradiction**, not factual error.
- **Feature at beta level**: Topic overlap with stored material provides a coarse consistency signal. For highly multi-topic writing, this feature may not activate.

---

## Character Extraction

### Hash-Based Deterministic Selection

```python
def extract_chars(text, conv_num, k=5):
    seed = f"{text}{conv_num}"
    h = hashlib.sha256(seed.encode()).hexdigest()
    positions = [int(h[i*8:(i+1)*8], 16) % len(text) for i in range(k)]
    return "".join(text[p] for p in sorted(positions))
```

Properties:
- Deterministic: same text + same conv_num → same output
- Uniform distribution: SHA-256 ensures even spread
- No configurable parameters (only k, which is fixed)

### Habit Profile Weighted Extraction (Active Phase only)

The response text is divided into N bins (default: 5). Each bin tracks how many extracted characters fell into it. Over time this forms a probability distribution showing where the model tends to place its answers.

```python
def weighted_extract_from_profile(text, conv_num, profile, k=5):
    # Step 1: Use hash to select a bin (weighted by profile probabilities)
    # Step 2: Within the selected bin, use hash to select a character position
    # Result: Characters are biased toward the model's typical answer region
```

---

## Fuzzy Matching

### Algorithm

Python's `difflib.SequenceMatcher.ratio()` — standard library, zero dependencies.

Returns a float in [0.0, 1.0]:
- 1.0 = identical strings
- 0.0 = no common characters
- Formula: `2.0 * M / T` (M = matching characters, T = total characters)

### Scoring

When similarity < 80% (0.8), a hybrid penalty is applied:

```python
fuzzy_score = max(50, (100 - similarity_pct) * 2.5)
```

| Similarity | Score | Rationale |
|------------|-------|-----------|
| >= 80% | 0 | Within acceptable range, no penalty |
| 79% | 52 | Minor deviation, minimum penalty applied |
| 60% | 100 | Significant deviation, proportional scaling |
| 30% | 175 | Major inconsistency, heavy penalty |
| 0% | 250 | Complete mismatch, maximum penalty |

---

## Token Counting

Uses OpenAI's `tiktoken` library with `cl100k_base` encoding (matching Claude's tokenizer).

Output: `{ input_tokens, output_tokens, total_tokens }`

Redundancy counter increments: `+10 per 1,000,000 total tokens`.

---

## Decision Formula

```
T = threshold         (initial: 1,000,000, adjustable by learning layer)
S = subjective_count  (keyword matches in this response)
R = redundancy_count  (token-based, cumulative)
F = fuzzy_score       (from cross-session comparison)

trigger_score = S + R + F

if (trigger_score - T) >= 0 → trigger Web Fetch verification
else → no action
```

### Display to user

```
display_pct = (S + R + F) / T × 100%

0%   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  100%
     ↑ Safe zone                         ↑ Trigger
```

---

## Habit Profile

A 5-bin probability distribution over the response text:

```
Response: "北京是中国的首都，位于华北平原..."
           ┌─────┬─────┬─────┬─────┬─────┐
Bins:      |  1  |  2  |  3  |  4  |  5  |
           └─────┴─────┴─────┴─────┴─────┘
           bin_counts: [5, 12, 10, 5, 3]
           → dominant_bin: 2 (answer typically starts in mid-front)
```

Updated after every response. Used in Active phase to bias character extraction toward high-probability regions.

---

## Data Flow

```
[Model generates response]
         │
         ▼
┌──────────────────────────────────┐
│ 1. Extract topic signature       │  ← topic_embed.py (self-persists)
│ 2. Append new turn entry         │  ← session_store.py
│ 3. Count subjective keywords     │  ← inline, session_store.py persist
│ 4. Count tokens                  │  ← count_tokens.py (self-persists)
│ 5. Hash-extract chars + fuzzy    │  ← fuzzy_match.py (self-persists)
│ 6. Decision formula (three-zone) │  ← inline, session_store.py persist
│ 7. Reference material check      │  ← reference_material.py (self-persists)
│ 8. Update habit_profile          │  ← calc_habit.py (self-persists)
│ 9. Adaptation                    │  ← adapt_threshold.py (reads turns.json)
│10. Correction (if triggered)     │  ← correction.py (self-persists)
└──────────────────┬───────────────┘
                   │
                   ▼
[Display shelter card if Mark/Verify]
                   │
                   ▼
[If Verify → Web Fetch verification]
```

---

## File Structure

```
{project_root}/
└── hallucination-watch/
    ├── params.json                   # (Learning layer) dynamic overrides
    └── sessions/{session_id}/
        ├── session.json              # Session metadata + habit profile + cumulative
        ├── turns.json                # Per-turn metric array (core data store)
        └── reference.json            # Reference material entries

~/.config/opencode/skills/hallucination-watch/
    ├── SKILL.md
    ├── README.md
    ├── scripts/
    │   ├── session_store.py          # Unified data access layer (turns.json + session.json)
    │   ├── init_skill.py             # Session initialisation
    │   ├── calibrate_threshold.py    # Baseline calibration (dynamic N)
    │   ├── adapt_threshold.py        # EMA self-adaptation
    │   ├── correction.py             # Claim prioritization + A/B selection
    │   ├── count_tokens.py           # Token counting (tiktoken)
    │   ├── fuzzy_match.py            # Hash extraction + fuzzy comparison
    │   ├── calc_habit.py             # Habit profile computation
    │   ├── topic_embed.py            # Topic signature + Jaccard similarity
    │   ├── reference_material.py     # Reference material store + consistency
    │   └── complexity_estimator.py   # Question complexity → thinking estimate
    ├── tools/
    │   ├── compare_models.py         # Multi-model offline comparison
    │   └── e2e_test.py               # End-to-end pipeline test
    ├── references/
    │   └── algorithm-spec.md
    └── params/
        └── default.json
```

---

## Self-Adaptation Layer

File: `scripts/adapt_threshold.py`

A periodic module that reads `turns.json`, analyzes historical trigger patterns, and auto-tunes the threshold. Runs every `adaptation_interval` conversations (default: 10).

### Algorithm (Two-Stage)

```
Input:  turns.json → turns[].phase, triggered, formula_raw
        params/default.json (current parameters)

Stage 1 — Trigger Rate Feedback (Primary):
  active_results = [r for r in results if r.phase == "active"]
  current_rate = count(triggered) / len(active_results)

  if current_rate > target_rate + margin:
      threshold *= threshold_increase_factor    (default *1.10)
  elif current_rate < target_rate - margin:
      threshold *= threshold_decrease_factor    (default *0.90)

  Purpose: Maintain trigger rate near target (default 10%).

Stage 2 — EMA Pull (Safety Net):
  formula_raws = last 20 active results
  ema = EMA(formula_raws, alpha=0.3)

  if threshold / ema > 100:
      threshold = ema * 50

  Purpose: Prevent threshold from drifting to absurd levels
           if all three counters stay near zero forever.

Output: hallucination-watch/params.json (overrides threshold)
```

### EMA Formula

```
ema_0  = formula_raw_0
ema_t  = α × ema_{t-1} + (1 - α) × formula_raw_t

α = 0.3 (default):
  - Recent values weighted more heavily
  - Responds fairly quickly to changes
```

### Parameter Reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| `target_trigger_rate` | 0.10 | Desired proportion of conversations triggering Web Fetch |
| `rate_margin` | 0.02 | Dead zone around target rate (0.08 ~ 0.12 = no adjustment) |
| `threshold_increase_factor` | 1.10 | Multiply threshold by this when trigger rate too high |
| `threshold_decrease_factor` | 0.90 | Multiply threshold by this when trigger rate too low |
| `ema_alpha` | 0.3 | EMA smoothing factor (0=full historical, 1=only latest) |
| `adaptation_interval` | 10 | Run adaptation every N conversations |

### Edge Cases

| Situation | Behavior |
|-----------|----------|
| No turns.json or no active turns | Skipped (first conversation or still in baseline) |
| No active phase data | Skipped (still in baseline) |
| Trigger rate exactly at target | No change |
| Threshold would go below 1 | Clamped to 1 |
| EMA raw = 0 and threshold = 1M | Not triggered (ratio = infinite, but ema_raw > 0 check fails)

---

## Self-Correction Layer

File: `scripts/correction.py`

### Overview

When the decision formula triggers, the correction layer verifies the model's response using a two-direction approach:

- **Direction B** (Internal Self-Consistency): Zero-cost internal thinking, compares two independent reasoning paths.
- **Direction A** (Claim Extraction + Web Fetch): Extracts factual claims, prioritizes by risk signal, verifies top N via Web Fetch.

### Selection Mechanism

```
On trigger:
  is_first_trigger? ─→ Yes → Run A+B (establish baseline)
       │ No
       ▼
  Check B-path historical accuracy:
    b_accuracy < 0.8? ─→ Yes → Run A only (B unreliable)
       │ No
       ▼
  Check token budget:
    usage < 80%? ─→ Yes → Run A+B (sufficient budget)
       │ No
       ▼
  Run B only (budget saving)
    If B detects divergence → escalate to A
```

### Decision Logic (Script)

The `correction.py` script handles the decision via `decide_method()`:

```python
def decide_method(history, params):
    first_trigger = not history.get("correction_method")
    b_accuracy = history.get("b_path_accuracy", 0.5)
    b_min = params.get("b_path_min_accuracy", 0.8)
    token_pct = params.get("token_usage_pct", 0)

    if first_trigger:
        return {"use_b": True, "use_a": True, "reason": "first_trigger"}
    if b_accuracy < b_min:
        return {"use_b": False, "use_a": True, "reason": "b_path_unreliable"}
    if token_pct < 80:
        return {"use_b": True, "use_a": True, "reason": "sufficient_budget"}
    return {"use_b": True, "use_a": False, "reason": "budget_saving"}
```

### Direction B — Internal Self-Consistency

**Cost:** ~200-500 thinking tokens. Zero external API calls.

**Process:**
1. Re-read user question
2. Re-derive answer through independent reasoning path
3. Compare factual claims in both paths
4. If all claims agree → high confidence, skip Direction A
5. If claims diverge → mark specific claims, escalate to Direction A

### Direction A — Claim Extraction + Verification

**Cost:** 1-3 Web Fetch calls per trigger.

**Step 1: Claim prioritization (script)**

Each claim is scored by `score_claim()`:

| Factor | Weight | Rationale |
|--------|--------|-----------|
| Near subjective keyword | +30 | Overconfident phrasing increases risk |
| Fuzzy match score/10 | fuzzy/10 | Cross-session inconsistency signal |
| Short claim (<30 chars) | +10 | Cheaper and faster to verify |
| Medium claim (30-60 chars) | +5 | Moderate cost |

**Step 2: Batch Web Fetch**

Top N claims (default 5) are fetched in parallel. Each result is compared against the original claim.

**Step 3: Correction output**

If any claim is wrong, a correction block is appended after the original response:

```
[自我纠错 / Self-Correction]
 发现 1/3 条声明需修正:

 • 原: "法国的首都是里昂"
   正: "法国的首都是巴黎"

 修正率: 33% | 方法: A+B | B路径: 一致
```

### turns.json Extension

Correction data is stored in each record's `correction` field:

```json
{
  "correction": {
    "method": "A+B",
    "b_path_agreed": true,
    "claims_extracted": 5,
    "claims_verified": 3,
    "claims_wrong": 1,
    "correction_applied": true
  }
}
```

### Feedback to Adaptation Layer

Two new signals flow from correction → adaptation:

| Signal | Source | Effect on Threshold |
|--------|--------|-------------------|
| `correction_rate` | Direction A results | Higher correction rate → lower threshold (more cautious) |
| `b_path_accuracy` | Direction B vs final outcome | Higher accuracy → trust B more (cost saving) |

### Parameter Reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| `b_path_min_accuracy` | 0.8 | Minimum B-path accuracy to trust B-only decisions |
| `max_claims_per_trigger` | 5 | Maximum claims to verify per Direction-A run |
| `correction_enabled` | true | Master switch for self-correction |

---

## User Feedback Channel

### Design Principle

User corrections are **informational, not algorithmic**. The user may be wrong, so their feedback is never used as ground truth for threshold adaptation.

### Two Independent Signals

| Signal | Source | Used For |
|--------|--------|----------|
| `correction_applied` | Direction A (Web Fetch) | Adaptation layer (correction_rate) |
| `user_contested` | User said "不对"/"wrong" | Display only + force re-verify |

### Storage

In turns.json (per-turn `correction` field):

```json
{
  "method": "A",
  "correction_applied": true,
  "user_contested": true,
  "user_contested_at": "2026-06-07T16:30:00Z"
}
```

### Behavior on User Correction

1. Record `user_contested=true` in the latest record (NO effect on correction_rate)
2. Force-run Direction A (claim extraction + Web Fetch)
3. Display verification result to user
4. If Web Fetch confirms user was right → set `correction_applied=true` normally
5. If Web Fetch confirms user was wrong → display "已验证原回答正确"

This prevents the self-amplifying error loop where wrong user feedback distorts the threshold.
