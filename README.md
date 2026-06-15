# Hallucination Watch / 幻觉监测系统

> **A behavioral-proxy hallucination risk monitor for LLM conversations.**
> **基于行为代理信号的 LLM 对话幻觉风险监控系统。**

[English](#english) | [中文](#中文)

---

<a name="english"></a>

## English

### 1. Overview

**Hallucination Watch** is an opencode skill that continuously screens LLM conversations for hallucination risk using **behavioral proxy signals** — it does not require a second model, external fact databases, or expensive inference. Instead, it analyzes patterns in the model's own output (subjective language, cross-session consistency, token accumulation) to estimate hallucination probability.

**Key Philosophy:** The system is a pre-filter, not a definitive fact-checker. It identifies *which* responses warrant deeper verification, so you don't manually review every answer. It is designed to be cheap (~200-500 thinking tokens per turn, zero API calls in the safe zone) and fully transparent.

**Activation:** User-activated — say `start monitoring` / `启动幻觉监测` to begin. Stays silent unless risk is detected.

---

### 2. Architecture Overview

```
                     ┌─────────────────────────────────────┐
                     │         Model generates response     │
                     └──────────────┬──────────────────────┘
                                    │
                     ┌──────────────▼──────────────────────┐
                     │      Behavioral Proxy Pipeline       │
                     │                                      │
                     │  1. Subjective Keyword Counting      │
                     │  2. Character Extraction (hash)      │
                     │  3. Cross-Session Fuzzy Comparison   │
                     │  4. Token Counting + Redundancy       │
                     │  5. Topic Tracking (Jaccard)         │
                     │  6. Material Consistency Check       │
                     │  7. Habit Profile Update             │
                     └──────────────┬──────────────────────┘
                                    │
                     ┌──────────────▼──────────────────────┐
                     │        Decision Formula (3-Zone)     │
                     │                                      │
                     │  Green  (<100%) → Safe, no action    │
                     │  Yellow (100-200%) → Mark, optional  │
                     │  Red   (≥200%) → Verify, auto-correct│
                     └──────────────┬──────────────────────┘
                                    │
                     ┌──────────────▼──────────────────────┐
                     │     Self-Correction Layer            │
                     │                                      │
                     │  Direction B (internal, zero API)    │
                     │  Direction A (Web Fetch, 1-3 calls)  │
                     └─────────────────────────────────────┘
```

---

### 3. Behavioral Proxy Signals

The system uses three independent proxy signals, each capturing a different dimension of hallucination risk:

#### 3.1 Subjective Keyword Counting

**Hypothesis:** Overconfident or definitive language correlates with higher hallucination risk. When the model says "definitely" or "absolutely", it is more likely to be wrong than when it hedges.

**Keywords tracked (density-normalized):**

| Chinese | English translation |
|---------|-------------------|
| 一定 | certainly / must |
| 绝对是 | absolutely is |
| 肯定 | definitely / surely |
| 必然 | inevitably |
| 毫无疑问 | without a doubt |
| 必须 | must |
| 不可能 | impossible |
| 总是 | always |
| 永远 | forever / always |
| 从来都 | has always been |
| 绝不 | never |
| 一定不会 | certainly will not |
| 肯定不 | definitely not |
| 绝对不 | absolutely not |

**Density Normalization:** Raw keyword count is divided by response token count, then multiplied by `density_multiplier` (default: 1000). This prevents false positives on long-form content (novels, papers) where keyword count naturally scales with length.

```
density_subjective = (subjective_count / max(response_tokens, 1)) × 1000
```

| Scenario | Old (raw) | New (density) | Correct? |
|----------|-----------|---------------|----------|
| Short Q&A (200 tok, 3 keywords) | 3 | 15 | ✓ baseline |
| Novel chapter (8K tok, 60 keywords) | **60** (false positive) | **7.5** | ✓ fixed |

#### 3.2 Cross-Session Fuzzy Matching

**Hypothesis:** If the model gives inconsistent answers to similar questions across sessions, at least one answer is likely wrong.

**Character Extraction (Hash-Based):**
```python
def extract_chars(text, conv_num, k=5):
    seed = f"{text}{conv_num}"
    h = hashlib.sha256(seed.encode()).hexdigest()
    positions = [int(h[i*8:(i+1)*8], 16) % len(text) for i in range(k)]
    return "".join(text[p] for p in sorted(positions))
```
- Deterministic: same text + same conv_num → same output
- Uniform distribution via SHA-256
- Only `k=5` characters extracted per response (minimal storage)

**Fuzzy Comparison (difflib.SequenceMatcher):**
```python
similarity = SequenceMatcher(None, chars_a, chars_b).ratio()
# similarity ∈ [0.0, 1.0]
```

**Scoring:** When similarity < 80%, a hybrid penalty is applied:
```python
fuzzy_score = max(50, (100 - similarity_pct) × 2.5)
```

| Similarity | Score | Meaning |
|------------|-------|---------|
| ≥ 80% | 0 | Acceptable consistency |
| 79% | 52 | Minor deviation |
| 60% | 100 | Significant inconsistency |
| 30% | 175 | Major inconsistency |
| 0% | 250 | Complete mismatch |

**Phase gating:** In **baseline** phase, fuzzy score is always 0 (recording only). In **active** phase, topic drift is detected first: if the current session's topic is different from the previous session's (Jaccard similarity < 0.15), fuzzy score is zeroed out to prevent noise from cross-topic comparison.

#### 3.3 Token Redundancy

**Hypothesis:** Research shows that LLM accuracy degrades as cumulative context length increases. Longer conversations warrant higher scrutiny.

**Research support:**

| Paper | Year | Key Finding |
|-------|------|-------------|
| **Lost in the Middle** (Liu et al., TACL) | 2023 | Accuracy drops from ~85% to ~60% as context expands from 10 to 30 documents. Performance degrades monotonically with token count. |
| **Limits of Long-Context Reasoning** (ICLR) | 2026 | Successful LLM trajectories stay under 20–30K tokens. At 64K tokens, solve rate drops to 7%. Longer cumulative contexts strongly correlate with failure. |
| **U-NIAH** | 2025 | Long context leads to systematic hallucination patterns: omission, false claims, and self-doubt under high noise conditions. |

**Implementation:**
```python
redundancy_score = floor(cumulative_total / 1,000,000) × 10
```
- Increments at every 1,000,000 total tokens
- Uses `tiktoken` with `cl100k_base` encoding
- Thinking tokens are estimated via `complexity_estimator.py` and included in the cumulative total

---

### 4. Topic Tracking

**File:** `scripts/topic_embed.py`

Cross-session fuzzy comparison is only meaningful when both conversations share the same topic. Topic tracking prevents false signals from topic drift.

**Approach:** Jaccard similarity on content words.

```python
def extract_topic_sig(text):
    ascii_words = re.findall(r'[a-zA-Z]+', text.lower())
    cjk_chars = re.findall(r'[\u4e00-\u9fff]', text)
    all_tokens = [w for w in ascii_words if len(w) > 1] + cjk_chars
    return dict(Counter(t for t in all_tokens if t not in STOP_WORDS).most_common(10))

def topic_similarity(sig_a, sig_b):
    set_a, set_b = set(sig_a.keys()), set(sig_b.keys())
    return len(set_a & set_b) / len(set_a | set_b) if set_a and set_b else 0.0
```

**Decision** (threshold: 0.15):

| Similarity | Behavior |
|------------|----------|
| ≥ 0.15 | Same topic → normal fuzzy comparison |
| < 0.15 | Different topic → fuzzy_score = 0, record `topic_drift = true` |

---

### 5. Decision Formula (Three-Zone)

The original binary trigger is replaced with three zones to give users control over verification cost.

#### Formula

```
trigger_score = density_subjective + fuzzy_score + redundancy_score + material_inconsistency
display_pct   = (trigger_score / threshold) × 100%

T = threshold (initial: 1,000,000, automatically calibrated at baseline→active transition)
```

#### Three Zones

| Zone | Condition | Display | Action | Cost |
|------|-----------|---------|--------|------|
| **Green** | display_pct < 100% | Safe/Watch (silent) | None | 0 |
| **Yellow** | 100% ≤ display_pct < 200% | Shelter card: ⚑ detected, prompt `verify` | User opts in | 0 (unless user says verify) |
| **Red** | display_pct ≥ 200% | Shelter card: auto-verify | Direction A+B or A | 1-3 Web Fetch calls |

#### Monthly Budget

```json
{ "web_fetch_monthly_budget": 200 }
```

When monthly budget is exhausted, Red zone triggers are demoted to Yellow (Mark + prompt). Budget resets on day 1 of each month.

---

### 6. Two-Phase Algorithm

#### Phase 1: Baseline (Conversations 1 ~ N)

| Property | Value |
|----------|-------|
| Duration | Dynamic N (min: 6, max: 20), data-driven |
| Behavior | All counters run, formula_raw recorded |
| Web Fetch | NEVER triggered (threshold effectively infinite) |
| Purpose | Build habit_profile, collect baseline data for calibration |

**Dynamic N (Variance-Based Extension):**
```python
n = current baseline record count
if n < min_baseline_n (6):            → stay in baseline
if n >= 6 AND n < 20:
    cv = std / mean  # coefficient of variation
    if cv <= 0.3:                     → calibrate, transition to active
    else:                             → extend baseline (behavior unstable)
if n >= 20:                            → force calibrate regardless
```

**Rationale:** If the model's formula_raw values are highly variable in the first 6 conversations, it hasn't settled into a predictable pattern yet. Extending baseline prevents a bad initial threshold.

#### Phase 2: Active (Conversation N+1 onwards)

| Property | Value |
|----------|-------|
| Calibration threshold | `max(mean_raw + 3.0 × std_raw, min_threshold=100)` |
| Behavior | Full detection with habit-profile weighted character extraction |
| Web Fetch | Triggered on Red zone (≥200%) |

**Calibration example:**

| Model Personality | Baseline Raw | Std | Threshold |
|------------------|-------------|-----|-----------|
| Cautious | ~40 | ~10 | max(40+30, 100) = 100 |
| Confident | ~200 | ~40 | max(200+120, 100) = 320 |
| Variable | ~150 | ~80 | cv=0.53 > 0.3 → extend baseline |

---

### 7. Habit Profile

A 5-bin probability distribution over the response text, tracking where the model typically places answers.

```
Response: "Paris is the capital of France, located in..."
           ┌─────┬─────┬─────┬─────┬─────┐
Bins:      |  1  |  2  |  3  |  4  |  5  |
           └─────┴─────┴─────┴─────┴─────┘
           bin_counts: [5, 12, 10, 5, 3]
           → dominant_bin: 2 (answer typically starts in mid-front)
```

Updated after every response. In Active phase, character extraction is biased toward high-probability bins via `calc_habit.py`:

```python
def weighted_extract_from_profile(text, conv_num, profile, k=5):
    # Step 1: Use hash to select a bin (weighted by profile probabilities)
    # Step 2: Within selected bin, use hash to select a character position
    # Result: Characters are biased toward the model's typical answer region
    #         → more sensitive comparison on the part of the text that matters
```

---

### 8. Reference Material Anchoring

**Motivation:** During sustained research or writing, the user collects facts from model responses. If the model later contradicts its own previously stated facts, this is a strong hallucination signal.

**Collection Mode:** Automatically enters after 3+ consecutive same-topic conversations (no topic drift). Indicates sustained research/writing activity.

**Storage:** `reference_material.json` in skill data directory.

**Consistency Check (per-response):**
```python
def topic_overlap(sig_a, sig_b):
    set_a, set_b = set(sig_a.keys()), set(sig_b.keys())
    return len(set_a & set_b) / len(set_a | set_b)

if overlap >= 0.15:
    matches = count(stored entries with overlap ≥ 0.15)
    material_inconsistency = max(0, 40 - matches × 8)
```

This penalty feeds into the decision formula.

**Limitations:**
- Topic-gated: only activates after 3 consecutive same-topic conversations.
- Self-referential: stores model statements, not verified facts. Detects **self-contradiction**, not factual error.

---

### 9. Self-Adaptation Layer

**File:** `scripts/adapt_threshold.py`

**Frequency:** Every `adaptation_interval` (default: 10) conversations during Active phase.

**Purpose:** Automatically tune the threshold to maintain a target trigger rate (~10%).

#### Algorithm (Two-Stage)

**Stage 1 — Trigger Rate Feedback (Primary):**
```python
active_results = filter(phase == "active")
current_rate = count(triggered) / len(active_results)

if current_rate > 0.10 + 0.02:       # too sensitive
    threshold *= 1.10                 # raise threshold
elif current_rate < 0.10 - 0.02:     # too insensitive
    threshold *= 0.90                 # lower threshold
```

**Stage 2 — EMA Pull (Safety Net):**
```python
ema = EMA(last_20_formula_raws, alpha=0.3)
if threshold / ema > 100:
    threshold = ema × 50              # prevent absurd drift
```

#### Parameter Reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| `target_trigger_rate` | 0.10 | Desired proportion of conversations triggering Web Fetch |
| `rate_margin` | 0.02 | Dead zone: 0.08–0.12 = no adjustment |
| `threshold_increase_factor` | 1.10 | Multiply threshold when trigger rate too high |
| `threshold_decrease_factor` | 0.90 | Multiply threshold when trigger rate too low |
| `ema_alpha` | 0.3 | EMA smoothing factor (0=full history, 1=only latest) |
| `adaptation_interval` | 10 | Run every N conversations |

---

### 10. Self-Correction Layer

**File:** `scripts/correction.py`

When the decision formula triggers, the correction layer verifies the response using a two-direction approach.

#### Selection Mechanism (Dynamic)

```
On trigger:
  is_first_trigger? ─→ Yes → Run A+B (establish baseline)
       │ No
       ▼
  B-path historical accuracy:
    < 80%? ─→ Yes → Run A only (B unreliable)
       │ No
       ▼
  Token budget:
    < 80% used? ─→ Yes → Run A+B (sufficient budget)
       │ No
       ▼
  Run B only (budget saving)
    If divergence detected → escalate to A
```

#### Direction B — Internal Self-Consistency

| Aspect | Detail |
|--------|--------|
| **Cost** | ~200-500 thinking tokens, zero external API |
| **Visibility** | Runs entirely in internal thinking (invisible to user) |
| **Method** | Re-reads question, re-derives answer via independent reasoning path, compares factual claims |
| **Outcome** | Paths agree → high confidence, skip Direction A. Divergence → mark claims, escalate |

#### Direction A — Claim Extraction + Web Fetch

| Aspect | Detail |
|--------|--------|
| **Cost** | 1-3 Web Fetch calls per trigger |
| **Trigger** | Auto on Red zone; optional on Yellow zone (user says `verify`) |

**Claim prioritization** (scored by `correction.py`):

| Factor | Weight | Rationale |
|--------|--------|-----------|
| Near subjective keyword | +30 | Overconfident phrasing increases risk |
| Fuzzy match score / 10 | score/10 | Cross-session inconsistency signal |
| Short claim (<30 chars) | +10 | Cheaper and faster to verify |
| Medium claim (30-60 chars) | +5 | Moderate cost |

Top N claims (default: 5) are verified via Web Fetch. Results are compared against original claims.

#### Correction Output Format

When errors are found:
```
─── hallucination-shelter ────
 ✓ 已修正 1 处
 → "法国的首都是巴黎"
────────────────────────────
```

When Direction B confirms consistency:
```
─── hallucination-shelter ────
 ✓ 验证一致
────────────────────────────
```

#### permanent.json Correction Record

```json
{
  "correction": {
    "method": "A+B",
    "b_path_agreed": true,
    "claims_extracted": 5,
    "claims_verified": 3,
    "claims_wrong": 1,
    "correction_applied": true,
    "user_contested": false,
    "user_contested_at": null
  }
}
```

---

### 11. User Feedback Channel

**Principle:** User corrections are informational, not algorithmic. The user may be wrong, so their feedback is never used as ground truth for threshold adaptation.

**Trigger keywords:** `不对`, `错了`, `不是`, `你错了`, `更正`, `wrong`, `incorrect`, `not right`, `不`, `错`

**Behavior:**
1. Record `user_contested=true` in permanent.json (NO effect on correction_rate)
2. Force-run Direction A (claim extraction + Web Fetch)
3. Display verification result
4. If Web Fetch confirms user → set `correction_applied=true`
5. If Web Fetch confirms model → display "已验证原回答正确"

This prevents the self-amplifying error loop where wrong user feedback distorts the threshold.

---

### 12. Data Files

Per-session isolation with independent data files.

#### Project-Level Directory

```
{project_root}/
└── hallucination-watch/
    ├── params.json                     # Auto-generated threshold override (adaptation layer)
    ├── reference_material.json         # Shared material store (if applicable)
    └── sessions/
        ├── 2026-06-10_14-30-00/        # ← One per session
        │   ├── session.json            # Per-turn state (refreshed each turn)
        │   └── permanent.json          # All historical results for this session
        └── ...
```

| File | Purpose |
|------|---------|
| `sessions/{id}/session.json` | Current & previous conversation snapshot. Refreshed every turn. Contains current metrics, habit profile, topic signature. |
| `sessions/{id}/permanent.json` | Append-only record of every turn's metrics. Contains timestamps, scores, correction history, and user feedback. |
| `params.json` | (Auto-generated) Dynamic threshold override from adaptation layer. Overrides `default.json` values. |
| `reference_material.json` | (Auto-generated) Stored claims for material consistency check. |

#### Skill Directory Structure

```
~/.config/opencode/skills/hallucination-watch/
├── SKILL.md                        # Model instructions (trigger phrases, pipeline steps)
├── README.md                       # This file
├── LICENSE                         # MIT
├── scripts/
│   ├── init_skill.py               # Creates data dir, session.json, permanent.json
│   ├── count_tokens.py             # Token counting (tiktoken, cl100k_base)
│   ├── fuzzy_match.py              # Hash extraction + fuzzy comparison
│   ├── calc_habit.py               # Habit profile computation
│   ├── topic_embed.py              # Topic signature + Jaccard similarity
│   ├── complexity_estimator.py     # Thinking token estimation
│   ├── calibrate_threshold.py      # Baseline calibration (dynamic N, variance-based)
│   ├── adapt_threshold.py          # EMA self-adaptation (trigger rate feedback)
│   ├── correction.py               # Claim prioritization + A/B selection
│   └── reference_material.py       # Material store + consistency check
├── tools/
│   ├── e2e_test.py                 # End-to-end pipeline test
│   └── compare_models.py           # Multi-model offline comparison
├── references/
│   └── algorithm-spec.md           # Full technical specification
└── params/
    └── default.json                # All configurable parameters with defaults
```

---

### 13. Parameters Reference

| Parameter | Default | Description | Scope |
|-----------|---------|-------------|-------|
| `threshold` | 1,000,000 | Initial trigger threshold | Core |
| `min_baseline_n` | 6 | Minimum baseline conversations | Baseline |
| `max_baseline_n` | 20 | Maximum baseline before force-calibrate | Baseline |
| `variance_stable_threshold` | 0.3 | CV threshold for baseline extension (cv = std/mean) | Baseline |
| `calibration_multiplier` | 3.0 | Std multiplier for threshold = mean + multiplier × std | Calibration |
| `min_calibrated_threshold` | 100 | Floor value for calibrated threshold | Calibration |
| `adaptation_interval` | 10 | Run EMA adaptation every N conversations | Adaptation |
| `target_trigger_rate` | 0.10 | Desired Web Fetch trigger rate | Adaptation |
| `rate_margin` | 0.02 | Dead zone around target rate | Adaptation |
| `threshold_increase_factor` | 1.10 | Multiply threshold when too sensitive | Adaptation |
| `threshold_decrease_factor` | 0.90 | Multiply threshold when too insensitive | Adaptation |
| `ema_alpha` | 0.3 | EMA smoothing factor | Adaptation |
| `keyword_list` | [14 keywords] | Subjective keywords to count | Subjective |
| `density_multiplier` | 1000 | Density normalization factor | Subjective |
| `fuzzy_threshold` | 0.8 | Similarity threshold for fuzzy penalty | Fuzzy |
| `fuzzy_hybrid_base` | 50 | Minimum fuzzy penalty | Fuzzy |
| `fuzzy_hybrid_multiplier` | 2.5 | Scaling factor for fuzzy penalty | Fuzzy |
| `k_chars` | 5 | Number of characters to extract per response | Fuzzy |
| `num_bins` | 5 | Number of bins in habit profile | Habit |
| `topic_similarity_threshold` | 0.15 | Jaccard threshold for same-topic detection | Topic |
| `material_collection_threshold` | 0.15 | Jaccard threshold for material overlap | Material |
| `b_path_min_accuracy` | 0.8 | Min B-path accuracy to trust B-only decisions | Correction |
| `max_claims_per_trigger` | 5 | Max claims to verify per Direction A run | Correction |
| `correction_enabled` | true | Master switch for correction layer | Correction |
| `auto_verify_multiplier` | 2.0 | Red zone threshold multiplier (200%) | Correction |
| `web_fetch_monthly_budget` | 200 | Monthly Web Fetch call budget | Budget |
| `budget_reset_day` | 1 | Day of month for budget reset | Budget |
| `thinking_multiplier` | 3.0 | Estimated thinking = input_tokens × multiplier | Token |
| `redundancy_tokens_per_increment` | 1,000,000 | Tokens per redundancy increment | Token |
| `redundancy_increment` | 10 | Score increment per unit | Token |
| `redundancy_min_tpi` | 100,000 | Minimum tokens per increment (cap) | Token |
| `redundancy_max_tpi` | 10,000,000 | Maximum tokens per increment (cap) | Token |
| `redundancy_max_increment` | 50 | Maximum redundancy score | Token |

---

### 14. Display & Output

#### Normal (Safe/Watch) — Silent

No visible output for Green zone. The skill runs silently in the background.

#### Yellow Zone — Shelter Card (Mark)

```
─── hallucination-shelter ────
 ⚑ 检测到风险
 → 输入 'verify' 验证
────────────────────────────
```

#### Red Zone — Auto-Correction Display

When Direction A finds errors:
```
─── hallucination-shelter ────
 ✓ 已修正 1 处
 → "法国的首都是巴黎"
────────────────────────────
```

When Direction B confirms consistency:
```
─── hallucination-shelter ────
 ✓ 验证一致
────────────────────────────
```

#### Full Metrics Card (Baseline / Debug)

```
─── hallucination-watch ──────────────────
 Input: 847 | Output: 1,203 | Total: 2,050
 Subjective: 4 | FuzzyDiff: 76% | Redundancy: 0
 Risk: 0.01% | Threshold: 100% | Status: Safe
─────────────────────────────────────────
```

---

### 15. Limitations

| # | Limitation | Impact |
|---|-----------|--------|
| 1 | **Score is relative, not absolute.** Compares against model's own baseline, not an absolute hallucination probability. | Cannot say "this response has X% chance of hallucination." Only says "this response looks more risky than usual for this model." |
| 2 | **Subjective words ≠ hallucinations.** A correct claim can contain "absolutely." A wrong claim can use neutral language. | Signal is directional, not definitive. Used as one of three independent proxies. |
| 3 | **Cross-session comparison is topic-sensitive.** Topic tracking mitigates but does not eliminate noise from topic drift. | Some cross-topic comparisons still leak through. |
| 4 | **Direction B can share blind spots.** Both reasoning paths may use the same incorrect training knowledge. | Direction B confirms *self-consistency*, not *factual correctness*. |
| 5 | **No benchmark data available.** Accuracy has not been measured against a labeled hallucination dataset. | Actual false-positive and false-negative rates are unknown. |
| 6 | **Designed as a pre-filter.** Not a replacement for thorough fact-checking on critical content. | Use for screening, not for final verification. |
| 7 | **Density normalization assumes linearity.** Very short responses (<20 tokens) may have inflated density. | Single-word answers may trigger false positives. |
| 8 | **Reference material is topic-gated.** Only activates after 3 consecutive same-topic conversations. | Early-stage or highly multi-topic writing bypasses this protection. |
| 9 | **Material stores model statements, not verified facts.** Consistency check detects self-contradiction, not factual error. | Two wrong answers that agree = passes the check. |
| 10 | **Token redundancy uses estimated thinking tokens.** Ratio is self-calibrated, not precise. | Values are approximate, not exact measurements. |

---

### 16. Installation & Setup

```bash
# 1. Install tiktoken (required for token counting)
pip install tiktoken

# 2. Place skill in opencode skills directory
#    ~/.config/opencode/skills/hallucination-watch/

# 3. Activate by saying "start monitoring" or "启动幻觉监测"
```

---

### 17. Roadmap

- **v1.0** — Core algorithm: subjective counting, fuzzy matching, token tracking, binary decision formula ✅
- **v2.0** — Self-adaptation layer: dynamic threshold via EMA + trigger rate feedback ✅
- **v3.0** — Self-correction layer: two-direction verification (B: internal, A: Web Fetch) ✅
- **v3.1** — Reference material anchoring + density normalization ✅
- **v4.0** *(planned)* — Ground truth sampling: periodic user verification prompts to build labeled dataset for accuracy measurement
- **v4.1** *(planned)* — Multi-model comparison: run same pipeline across 2+ models and compare hallucination profiles

---

### 18. License

MIT

---

<a name="中文"></a>

## 中文

### 1. 概述

**Hallucination Watch（幻觉监测）** 是一个 opencode 技能，通过**行为代理信号**持续筛查 LLM 对话中的幻觉风险——无需第二个模型、外部事实数据库或昂贵的推理调用。它仅分析模型自身输出中的模式（主观语言、跨会话一致性、Token 累积量）来估算幻觉概率。

**核心理念：** 本系统是前置筛选器，而非确定性事实核查工具。它识别*哪些*回复值得深入验证，让你不必手动审阅每一条回答。设计上追求低成本（安全区每轮 200-500 thinking tokens，零 API 调用）和完全透明。

**激活方式：** 用户主动激活——说 `start monitoring` 或 `启动幻觉监测` 开始监控。未检测到风险时保持静默。

---

### 2. 系统架构

```
                     ┌─────────────────────────────────────┐
                     │          模型生成回复                    │
                     └──────────────┬──────────────────────┘
                                    │
                     ┌──────────────▼──────────────────────┐
                     │          行为代理信号流水线            │
                     │                                      │
                     │  1. 主观关键词计数 (密度归一化)         │
                     │  2. 特征字符提取 (哈希)                │
                     │  3. 跨会话模糊比对                     │
                     │  4. Token 计数 + 冗余计算              │
                     │  5. 话题追踪 (Jaccard)                │
                     │  6. 参考材料一致性检查                  │
                     │  7. 习惯剖面更新                       │
                     └──────────────┬──────────────────────┘
                                    │
                     ┌──────────────▼──────────────────────┐
                     │        三区决策公式                    │
                     │                                      │
                     │  绿区 (<100%) → 安全，无操作           │
                     │  黄区 (100-200%) → 标记，用户可选验证  │
                     │  红区 (≥200%) → 自动验证+修正          │
                     └──────────────┬──────────────────────┘
                                    │
                     ┌──────────────▼──────────────────────┐
                     │        自我纠错层                      │
                     │                                      │
                     │  B 方向 (内部推理，零 API 成本)         │
                     │  A 方向 (Web Fetch 验证，1-3 次调用)   │
                     └─────────────────────────────────────┘
```

---

### 3. 行为代理信号

系统使用三个独立的行为代理信号，每个信号捕捉幻觉风险的不同维度：

#### 3.1 主观关键词计数

**假设：** 过度自信或绝对化的语言与更高的幻觉风险相关。当模型说"绝对"或"毫无疑问"时，它比使用模糊表达时更可能出错。

**追踪的关键词（密度归一化）：**

| 中文 | 示例场景 |
|------|---------|
| 一定 | "这个方案一定可行" |
| 绝对是 | "这个结论绝对是正确的" |
| 肯定 | "他肯定是凶手" |
| 必然 | "必然导致系统崩溃" |
| 毫无疑问 | "毫无疑问这是最佳实践" |
| 必须 | "你必须安装这个依赖" |
| 不可能 | "这个方案不可能失败" |
| 总是 | "这个函数总是返回 true" |
| 永远 | "这个 bug 永远修不好" |
| 从来都 | "这个库从来都不支持中文" |
| 绝不 | "这个算法绝不比那个差" |
| 一定不会 | "这个特性一定不会出问题" |
| 肯定不 | "这个方案肯定不行" |
| 绝对不 | "绝对不要用这个方法" |

**密度归一化：**

```python
density_subjective = (subjective_count / max(response_tokens, 1)) × 1000
```

| 场景 | 旧(原始计数) | 新(密度归一化) | 改进 |
|------|------------|--------------|------|
| 短问答 (200 tok, 3 个关键词) | 3 | 15 | ✓ 基线正常 |
| 小说章节 (8K tok, 60 个关键词) | **60** (误报) | **7.5** | ✓ 消除误报 |

#### 3.2 跨会话模糊比对

**假设：** 如果模型在多次会话中对类似问题给出不一致的回答，则至少有一个回答很可能是错误的。

**特征字符提取（基于哈希）：**

```python
def extract_chars(text, conv_num, k=5):
    seed = f"{text}{conv_num}"
    h = hashlib.sha256(seed.encode()).hexdigest()
    positions = [int(h[i*8:(i+1)*8], 16) % len(text) for i in range(k)]
    return "".join(text[p] for p in sorted(positions))
```

- 确定性：相同文本 + 相同会话号 → 相同输出
- 通过 SHA-256 实现均匀分布
- 每次回复仅提取 5 个字符（最小化存储）

**模糊比对（difflib.SequenceMatcher）：**

```python
similarity = SequenceMatcher(None, chars_a, chars_b).ratio()
```

**评分规则：** 相似度 < 80% 时应用混合惩罚：

| 相似度 | 分数 | 含义 |
|--------|------|------|
| ≥ 80% | 0 | 可接受的一致性 |
| 79% | 52 | 轻微偏差 |
| 60% | 100 | 明显不一致 |
| 30% | 175 | 重大不一致 |
| 0% | 250 | 完全矛盾 |

**阶段控制：** 基线阶段模糊分数始终为 0（仅记录）。活跃阶段先检测话题漂移：若当前话题与上一会话不同（Jaccard < 0.15），模糊分数归零以防止跨话题噪声。

#### 3.3 Token 冗余

**假设：** 研究表明，随着累积上下文长度增加，LLM 准确率下降。更长的对话需要更高的审查力度。

**理论依据：**

| 论文 | 年份 | 关键发现 |
|------|------|---------|
| **Lost in the Middle** (Liu et al., TACL) | 2023 | 上下文从 10 文档扩展到 30 文档时，准确率从 ~85% 降至 ~60% |
| **Limits of Long-Context Reasoning** (ICLR) | 2026 | 成功对话轨迹通常在 20-30K tokens 以下；64K tokens 时解决率降至 7% |
| **U-NIAH** | 2025 | 长上下文导致系统性幻觉模式：遗漏、虚假声明、高噪声下的自我怀疑 |

**实现：**

```python
redundancy_score = floor(cumulative_total / 1,000,000) × 10
```

每 1,000,000 总 tokens 增加一次。使用 `tiktoken` 的 `cl100k_base` 编码。Thinking tokens 通过 `complexity_estimator.py` 估算并计入累积总量。

---

### 4. 话题追踪

**文件：** `scripts/topic_embed.py`

跨会话的模糊比对比较仅在两次对话话题相同时才有意义。话题追踪防止话题漂移带来的错误信号。

**方法：** 内容词的 Jaccard 相似度

```python
def extract_topic_sig(text):
    ascii_words = re.findall(r'[a-zA-Z]+', text.lower())
    cjk_chars = re.findall(r'[\u4e00-\u9fff]', text)
    all_tokens = [w for w in ascii_words if len(w) > 1] + cjk_chars
    return dict(Counter(t for t in all_tokens if t not in STOP_WORDS).most_common(10))

def topic_similarity(sig_a, sig_b):
    set_a, set_b = set(sig_a.keys()), set(sig_b.keys())
    return len(set_a & set_b) / len(set_a | set_b) if set_a and set_b else 0.0
```

**判定标准（阈值：0.15）：**

| 相似度 | 行为 |
|--------|------|
| ≥ 0.15 | 同话题 → 正常模糊比对 |
| < 0.15 | 不同话题 → fuzzy_score = 0，记录 topic_drift = true |

---

### 5. 决策公式（三区制）

原二元触发被替换为三区制，让用户控制验证成本。

#### 公式

```
trigger_score = density_subjective + fuzzy_score + redundancy_score + material_inconsistency
display_pct   = (trigger_score / threshold) × 100%

T = 阈值（初始：1,000,000，基线→活跃转换时自动校准）
```

#### 三个区域

| 区域 | 条件 | 显示 | 操作 | 成本 |
|------|------|------|------|------|
| **绿区** | display_pct < 100% | 安全/观察（静默） | 无 | 0 |
| **黄区** | 100% ≤ display_pct < 200% | 防护卡：⚑ 检测到风险，提示 verify | 用户自行决定 | 0（除非用户输入 verify） |
| **红区** | display_pct ≥ 200% | 防护卡：自动验证 | 方向 A+B 或 A | 1-3 次 Web Fetch |

#### 月度预算

```json
{ "web_fetch_monthly_budget": 200 }
```

每月预算耗尽后，红区触发降级为黄区（标记+提示）。预算在每月 1 日重置。

---

### 6. 两阶段算法

#### 阶段 1：基线（第 1 ~ N 次会话）

| 属性 | 值 |
|------|-----|
| 时长 | 动态 N（最小 6，最大 20），数据驱动 |
| 行为 | 所有计数器运行，formula_raw 记录 |
| Web Fetch | 永不触发（阈值在此时为无穷大） |
| 目的 | 构建习惯剖面，收集校准数据 |

**动态 N（基于方差扩展）：**

```python
n = 当前基线记录数
if n < min_baseline_n (6):            → 留在基线
if n >= 6 AND n < 20:
    cv = std / mean  # 变异系数
    if cv <= 0.3:                     → 校准，转入活跃
    else:                             → 扩展基线（行为不稳定）
if n >= 20:                            → 强制校准
```

**设计理由：** 如果模型在前 6 次会话中的 formula_raw 值高度波动，说明尚未形成可预测的模式。扩展基线可防止设定糟糕的初始阈值。

#### 阶段 2：活跃（第 N+1 次会话起）

| 属性 | 值 |
|------|-----|
| 校准阈值 | `max(mean_raw + 3.0 × std_raw, min_threshold=100)` |
| 行为 | 完整检测，使用习惯剖面加权特征提取 |
| Web Fetch | 红区触发（≥200%） |

---

### 7. 习惯剖面

一个 5 区概率分布，追踪模型通常在回复的哪个区域放置答案。

```
回复: "北京是中国的首都，位于华北平原..."
       ┌─────┬─────┬─────┬─────┬─────┐
区间:  |  1  |  2  |  3  |  4  |  5  |
       └─────┴─────┴─────┴─────┴─────┘
       bin_counts: [5, 12, 10, 5, 3]
       → dominant_bin: 2 (答案通常在靠前位置出现)
```

每次回复后更新。活跃阶段，特征提取偏向高概率区间：

```python
def weighted_extract_from_profile(text, conv_num, profile, k=5):
    # 步骤1：用哈希选择一个区间（按剖面概率加权）
    # 步骤2：在选中区间内，用哈希选择字符位置
    # 结果：字符偏向模型通常放置答案的区域
    #       → 对关键部分的比对更加敏感
```

---

### 8. 参考材料锚定

**动机：** 在持续研究或写作过程中，用户从模型回复中收集事实信息。如果模型后来与自身之前陈述的事实矛盾，这就是一个强烈的幻觉信号。

**收集模式：** 在连续 3 次以上同话题对话（无话题漂移）后自动进入，表示用户正在进行持续研究或写作。

**存储：** `reference_material.json`，位于技能数据目录。

**一致性检查（每次回复）：**

```python
def topic_overlap(sig_a, sig_b):
    set_a, set_b = set(sig_a.keys()), set(sig_b.keys())
    return len(set_a & set_b) / len(set_a | set_b)

if overlap >= 0.15:
    matches = count(存储条目中 overlap ≥ 0.15 的个数)
    material_inconsistency = max(0, 40 - matches × 8)
```

该惩罚值输入决策公式。

**局限性：**
- 受限于话题检测：仅在连续 3 次同话题对话后激活。
- 自我指涉：存储的是模型表述，而非验证后的事实。检测的是**自我矛盾**，而非事实错误。

---

### 9. 自主学习层

**文件：** `scripts/adapt_threshold.py`

**频率：** 活跃阶段每 `adaptation_interval`（默认 10）次对话运行一次。

**目的：** 自动调整阈值以维持目标触发率（~10%）。

#### 算法（两阶段）

**阶段 1 — 触发率反馈（主）：**

```python
active_results = filter(phase == "active")
current_rate = count(triggered) / len(active_results)

if current_rate > 0.10 + 0.02:       # 太敏感
    threshold *= 1.10                 # 调高阈值
elif current_rate < 0.10 - 0.02:     # 太迟钝
    threshold *= 0.90                 # 调低阈值
```

**阶段 2 — EMA 安全网：**

```python
ema = EMA(last_20_formula_raws, alpha=0.3)
if threshold / ema > 100:
    threshold = ema × 50              # 防止阈值漂移到荒谬值
```

#### 参数参考

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `target_trigger_rate` | 0.10 | 期望触发 Web Fetch 的对话比例 |
| `rate_margin` | 0.02 | 死区: 0.08–0.12 = 不调整 |
| `threshold_increase_factor` | 1.10 | 触发率过高时乘以此系数 |
| `threshold_decrease_factor` | 0.90 | 触发率过低时乘以此系数 |
| `ema_alpha` | 0.3 | EMA 平滑因子（0=全历史，1=仅最新） |
| `adaptation_interval` | 10 | 每 N 次对话运行一次 |

---

### 10. 自我纠错层

**文件：** `scripts/correction.py`

当决策公式触发时，纠错层通过双方向方法验证模型回复。

#### 选择机制（动态）

```
触发时：
  首次触发？─→ 是 → 运行 A+B（建立基线）
       │ 否
       ▼
  B 路径历史准确率：
    < 80%？─→ 是 → 只运行 A（B 不可靠）
       │ 否
       ▼
  Token 预算：
    < 80% 已用？─→ 是 → 运行 A+B（预算充足）
       │ 否
       ▼
  只运行 B（节省预算）
    如果检测到不一致 → 升级到 A
```

#### B 方向 — 内部自洽性

| 属性 | 详情 |
|------|------|
| **成本** | ~200-500 thinking tokens，零外部 API |
| **可见性** | 完全在内部 thinking 中运行（对用户不可见） |
| **方法** | 重新读取问题，通过独立推理路径重新推导答案，比较事实性声明 |
| **结果** | 路径一致 → 高置信度，跳过 A 方向。不一致 → 标记声明，升级到 A |

#### A 方向 — 声明提取 + Web Fetch 验证

| 属性 | 详情 |
|------|------|
| **成本** | 每次触发 1-3 次 Web Fetch 调用 |
| **触发** | 红区自动；黄区可选（用户输入 `verify`） |

**声明优先级评分：**

| 因素 | 权重 | 理由 |
|------|------|------|
| 靠近主观关键词 | +30 | 过度自信的措辞增加风险 |
| 模糊匹配分数 / 10 | score/10 | 跨会话不一致信号 |
| 短声明 (<30 字符) | +10 | 验证成本低、速度快 |
| 中等声明 (30-60 字符) | +5 | 中等成本 |

取前 N 条声明（默认 5 条）通过 Web Fetch 验证，结果与原始声明比对。

#### 修正输出格式

发现错误时：
```
─── hallucination-shelter ────
 ✓ 已修正 1 处
 → "法国的首都是巴黎"
────────────────────────────
```

B 方向验证一致时：
```
─── hallucination-shelter ────
 ✓ 验证一致
────────────────────────────
```

#### permanent.json 中的修正记录

```json
{
  "correction": {
    "method": "A+B",
    "b_path_agreed": true,
    "claims_extracted": 5,
    "claims_verified": 3,
    "claims_wrong": 1,
    "correction_applied": true,
    "user_contested": false,
    "user_contested_at": null
  }
}
```

---

### 11. 用户反馈通道

**原则：** 用户纠正是信息性的，而非算法性的。用户可能错误，因此其反馈永远不用作阈值调整的 ground truth。

**触发关键词：** `不对`, `错了`, `不是`, `你错了`, `更正`, `wrong`, `incorrect`, `not right`, `不`, `错`

**行为：**
1. 在 permanent.json 中记录 `user_contested=true`（不影响 correction_rate）
2. 强制运行 A 方向（声明提取 + Web Fetch）
3. 显示验证结果
4. 如果 Web Fetch 确认用户正确 → 正常设置 `correction_applied=true`
5. 如果 Web Fetch 确认模型正确 → 显示"已验证原回答正确"

这防止了错误用户反馈扭曲阈值的自放大误差循环。

---

### 12. 数据文件

每次会话完全隔离，拥有独立的数据文件。

#### 项目级目录

```
{project_root}/
└── hallucination-watch/
    ├── params.json                     # 自动生成的阈值覆盖（适应层）
    ├── reference_material.json         # 共享材料存储
    └── sessions/
        ├── 2026-06-10_14-30-00/        # ← 每次会话独立目录
        │   ├── session.json            # 每轮状态（每次刷新）
        │   └── permanent.json          # 该会话的全部历史记录
        └── ...
```

#### 技能目录结构

```
~/.config/opencode/skills/hallucination-watch/
├── SKILL.md                        # 模型指令（触发短语、流水线步骤）
├── README.md                       # 本文件
├── LICENSE                         # MIT
├── scripts/
│   ├── init_skill.py               # 创建数据目录、session.json、permanent.json
│   ├── count_tokens.py             # Token 计数
│   ├── fuzzy_match.py              # 哈希提取 + 模糊比对
│   ├── calc_habit.py               # 习惯剖面计算
│   ├── topic_embed.py              # 话题签名 + Jaccard 相似度
│   ├── complexity_estimator.py     # Thinking token 估算
│   ├── calibrate_threshold.py      # 基线校准（动态 N）
│   ├── adapt_threshold.py          # EMA 自主学习
│   ├── correction.py               # 声明优先级 + A/B 选择
│   └── reference_material.py       # 材料存储 + 一致性检查
├── tools/
│   ├── e2e_test.py                 # 端到端流水线测试
│   └── compare_models.py           # 多模型离线对比
├── references/
│   └── algorithm-spec.md           # 完整技术说明
└── params/
    └── default.json                # 所有可配置参数及默认值
```

---

### 13. 参数参考

| 参数 | 默认值 | 说明 | 范围 |
|------|--------|------|------|
| `threshold` | 1,000,000 | 初始触发阈值 | 核心 |
| `min_baseline_n` | 6 | 最小基线对话数 | 基线 |
| `max_baseline_n` | 20 | 最大基线对话数，超过则强制校准 | 基线 |
| `variance_stable_threshold` | 0.3 | 基线扩展的变异系数阈值 (cv = std/mean) | 基线 |
| `calibration_multiplier` | 3.0 | 阈值 = mean + multiplier × std 中的标准差乘数 | 校准 |
| `min_calibrated_threshold` | 100 | 校准后阈值下限 | 校准 |
| `adaptation_interval` | 10 | 每 N 次对话运行 EMA 适应 | 适应 |
| `target_trigger_rate` | 0.10 | 期望的 Web Fetch 触发率 | 适应 |
| `rate_margin` | 0.02 | 目标触发率死区 | 适应 |
| `threshold_increase_factor` | 1.10 | 触发率过高时阈值乘数 | 适应 |
| `threshold_decrease_factor` | 0.90 | 触发率过低时阈值乘数 | 适应 |
| `ema_alpha` | 0.3 | EMA 平滑因子 | 适应 |
| `keyword_list` | [14 个词] | 主观关键词列表 | 主观 |
| `density_multiplier` | 1000 | 密度归一化因子 | 主观 |
| `fuzzy_threshold` | 0.8 | 模糊惩罚的相似度阈值 | 模糊 |
| `fuzzy_hybrid_base` | 50 | 最小模糊惩罚 | 模糊 |
| `fuzzy_hybrid_multiplier` | 2.5 | 模糊惩罚缩放因子 | 模糊 |
| `k_chars` | 5 | 每次回复提取的字符数 | 模糊 |
| `num_bins` | 5 | 习惯剖面的区间数 | 习惯 |
| `topic_similarity_threshold` | 0.15 | 同话题检测的 Jaccard 阈值 | 话题 |
| `material_collection_threshold` | 0.15 | 材料重叠的 Jaccard 阈值 | 材料 |
| `b_path_min_accuracy` | 0.8 | 信任 B-only 决策的最低 B 路径准确率 | 纠错 |
| `max_claims_per_trigger` | 5 | 每次 A 方向验证的最大声明数 | 纠错 |
| `correction_enabled` | true | 纠错层总开关 | 纠错 |
| `auto_verify_multiplier` | 2.0 | 红区阈值乘数 (200%) | 纠错 |
| `web_fetch_monthly_budget` | 200 | 每月 Web Fetch 调用预算 | 预算 |
| `budget_reset_day` | 1 | 预算重置日 | 预算 |
| `thinking_multiplier` | 3.0 | 估算 thinking = input_tokens × 乘数 | Token |
| `redundancy_tokens_per_increment` | 1,000,000 | 每次增量所需 Token 数 | Token |
| `redundancy_increment` | 10 | 每次增量分数 | Token |
| `redundancy_min_tpi` | 100,000 | 每次增量的最小 Token 数（上限） | Token |
| `redundancy_max_tpi` | 10,000,000 | 每次增量的最大 Token 数（上限） | Token |
| `redundancy_max_increment` | 50 | 最大冗余分数 | Token |

---

### 14. 显示与输出

#### 正常（安全/观察）— 静默

绿区无可见输出，技能在后台静默运行。

#### 黄区 — 防护卡（标记）

```
─── hallucination-shelter ────
 ⚑ 检测到风险
 → 输入 'verify' 验证
────────────────────────────
```

#### 红区 — 自动修正显示

A 方向发现错误时：
```
─── hallucination-shelter ────
 ✓ 已修正 1 处
 → "法国的首都是巴黎"
────────────────────────────
```

B 方向验证一致时：
```
─── hallucination-shelter ────
 ✓ 验证一致
────────────────────────────
```

#### 完整指标卡片（基线/调试）

```
─── hallucination-watch ──────────────────
 Input: 847 | Output: 1,203 | Total: 2,050
 Subjective: 4 | FuzzyDiff: 76% | Redundancy: 0
 Risk: 0.01% | Threshold: 100% | Status: Safe
─────────────────────────────────────────
```

---

### 15. 局限性

| # | 局限 | 影响 |
|---|------|------|
| 1 | **分数是相对值，非绝对值。** 与模型自身基线比较，不是绝对的幻觉概率。 | 不能说"此回复有 X% 概率存在幻觉"，只能说"此回复比该模型平时更可疑"。 |
| 2 | **主观词 ≠ 幻觉。** 正确陈述可能包含"绝对"，错误陈述可能使用中性语言。 | 信号是方向性的，非决定性的。作为三个独立代理之一使用。 |
| 3 | **跨会话比对受话题漂移影响。** 话题追踪已缓解但无法完全消除噪声。 | 部分跨话题比对仍可能漏过。 |
| 4 | **B 方向可能存在共同盲区。** 两条推理路径可能同时使用相同的错误训练知识。 | B 方向确认的是*自洽性*，而非*事实正确性*。 |
| 5 | **无基准测试数据。** 准确率未经标记幻觉数据集验证。 | 实际假阳性和假阴性率未知。 |
| 6 | **设计为前置筛选器。** 不能替代针对关键内容的完整事实核查。 | 用于筛选，不用于最终验证。 |
| 7 | **密度归一化假设线性关系。** 超短回复（<20 tokens）的密度值可能偏高。 | 单字回答可能触发误报。 |
| 8 | **参考材料受限于话题检测。** 仅在同话题连续 3 次对话后激活。 | 初期或高度多话题写作会绕过此保护。 |
| 9 | **材料存储的是模型表述，非验证后的事实。** 检测自我矛盾而非事实错误。 | 两个一致但错误的答案 = 通过检查。 |
| 10 | **Token 冗余使用估算的 thinking tokens。** 比例由适应层自校准，非精确测量。 | 数值是近似值。 |

---

### 16. 安装与设置

```bash
# 1. 安装 tiktoken（Token 计数必需）
pip install tiktoken

# 2. 将技能放入 opencode skills 目录
#    ~/.config/opencode/skills/hallucination-watch/

# 3. 说 "start monitoring" 或 "启动幻觉监测" 激活
```

---

### 17. 开发路线

- **v1.0** — 核心算法：主观计数、模糊比对、Token 追踪、二元决策公式 ✅
- **v2.0** — 自主学习层：基于 EMA + 触发率反馈的动态阈值调整 ✅
- **v3.0** — 自我纠错层：双方向验证（B：内部自洽，A：Web Fetch）✅
- **v3.1** — 参考材料锚定 + 密度归一化 ✅
- **v4.0** *(计划中)* — Ground truth 采样：定期用户验证提示，构建用于准确率测量的标记数据集
- **v4.1** *(计划中)* — 多模型对比：在 2+ 个模型上运行相同流水线并比较幻觉剖面

---

### 18. 许可

MIT
