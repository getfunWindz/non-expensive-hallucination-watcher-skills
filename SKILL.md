---
name: hallucination-watch
description: "User-activated hallucination risk monitor. ONLY activates when the user explicitly says a trigger phrase like '启动幻觉监测', 'start monitoring', '幻觉检测', or 'hallucination check'. Does NOT auto-activate. Once triggered, creates an isolated session with its own data files. All conversations, questions, discussions, or writing within that session are monitored via behavioral proxy signals. Stays silent unless risk is detected. When user says 'stop monitoring' or '停止监测', the session ends."
---

# Hallucination Watch

User-activated hallucination risk screening. Per-session isolation with independent data files.

---

## Trigger Phrases

The user must say one of these to start a session:

| Language | Phrases |
|----------|---------|
| Chinese  | `启动幻觉监测` / `开始监测` / `幻觉检测` / `检测幻觉` / `激活shelter` |
| English  | `start monitoring` / `hallucination check` / `activate shelter` / `shelter on` |

To stop: `停止监测` / `stop monitoring` / `shelter off`

---

## Data Storage Architecture (v2)

Each session creates three JSON files inside `{project_root}/hallucination-watch/sessions/{session_id}/`:

| File | Purpose | Self-persisting |
|------|---------|-----------------|
| `session.json` | Session metadata, habit profile, cumulative counters | Via `calc_habit.py record` |
| `turns.json` | **Per-turn metric array** — every computation result | Via each script's `record` mode |
| `reference.json` | Reference material entries for consistency checks | Via `reference_material.py` |

### Why this design?

Each pipeline script has its own `record` mode that writes directly to `turns.json` or `session.json`. This eliminates the old problem where the agent had to manually construct and write JSON — if a script runs, its data is persisted automatically.

### session.json schema

```json
{
  "session_id": "2026-06-22_14-30-00",
  "project_dir": "C:\\Users\\...",
  "created_at": "2026-06-22T14:30:00+08:00",
  "phase": "baseline",
  "conversation_number": 12,
  "habit_profile": {
    "total_samples": 12,
    "dominant_bin": 2,
    "bin_probs": [0.15, 0.25, 0.30, 0.20, 0.10]
  },
  "cumulative": {
    "total_tokens": 452000,
    "alert_count": 0,
    "correction_count": 0,
    "trigger_count": 0
  }
}
```

### turns.json schema

```json
{
  "turns": [
    {
      "turn": 1,
      "timestamp": "2026-06-22T14:30:05+08:00",
      "phase": "baseline",

      "topic_signature": {"法国": 1, "首都": 1},

      "keyword_density": 0.0,
      "keyword_matches": [],

      "fuzzy_chars": "a3b7k",
      "fuzzy_similarity": 0.0,
      "fuzzy_score": null,

      "total_tokens": 580,
      "visible_tokens": 450,
      "estimated_thinking": 130,
      "thinking_multiplier": 3.0,

      "redundancy_score": 0,
      "material_inconsistency": 0,

      "formula_raw": 580,
      "formula_zone": "safe",
      "risk_score": 0.0,

      "triggered": false,

      "correction": null
    }
  ]
}
```

---

## Setup (On Trigger)

When a trigger phrase is detected, generate a timestamp-based session ID and initialise the three data files.

### Step 1: Generate session ID + init files

```powershell
$project_root = (Get-Location).Path
$skill_dir = "$env:USERPROFILE\.config\opencode\skills\hallucination-watch"
$session_id = (Get-Date -Format "yyyy-MM-dd_HH-mm-ss")

$init_input = @{ project_dir = $project_root; session_id = $session_id } | ConvertTo-Json -Compress
$init_result = $init_input | python "$skill_dir/scripts/init_skill.py"
$init_obj = $init_result | ConvertFrom-Json
$session_id = $init_obj.session_id
$is_first_time = $init_obj.is_first_time
```

On subsequent calls (same `$session_id`), `init_skill.py` increments `conversation_number` and returns the existing session.

### Step 2: Load config

```powershell
$local_params = Join-Path $project_root "hallucination-watch" "params.json"
if (Test-Path $local_params) {
    $params = Get-Content $local_params -Raw | ConvertFrom-Json
} else {
    $params = Get-Content (Join-Path $skill_dir "params" "default.json") -Raw | ConvertFrom-Json
}
```

### Step 3: Load session state + turns

```powershell
$session_path = Join-Path $project_root "hallucination-watch" "sessions" $session_id "session.json"
$turns_path = Join-Path $project_root "hallucination-watch" "sessions" $session_id "turns.json"
$session = Get-Content $session_path -Raw | ConvertFrom-Json
$turns_data = Get-Content $turns_path -Raw | ConvertFrom-Json
```

### Step 4: Determine phase + calibrate (baseline → active)

```powershell
$min_n = $params.min_baseline_n
$max_n = $params.max_baseline_n
if ($session.conversation_number -le $min_n) {
    $session.phase = "baseline"
} elseif ($session.conversation_number -gt $max_n) {
    $session.phase = "active"
} else {
    $cal_input = @{ project_dir = $project_root; skill_dir = $skill_dir; session_id = $session_id } | ConvertTo-Json -Compress
    $cal_result = $cal_input | python "$skill_dir/scripts/calibrate_threshold.py"
    $cal_obj = $cal_result | ConvertFrom-Json
    $session.phase = if ($cal_obj.status -eq "extend") { "baseline" } else { "active" }
}

if ($session.phase -eq "active" -and $is_first_time) {
    $cal_input = @{ project_dir = $project_root; skill_dir = $skill_dir; session_id = $session_id } | ConvertTo-Json -Compress
    $cal_input | python "$skill_dir/scripts/calibrate_threshold.py"
    # reload params after calibration
    if (Test-Path $local_params) { $params = Get-Content $local_params -Raw | ConvertFrom-Json }
}

$session | ConvertTo-Json -Depth 10 | Set-Content $session_path
```

### Step 5: Extract topic signature

```powershell
$topic_input = @{ mode = "extract"; text = $user_message } | ConvertTo-Json -Compress
$topic_result = $topic_input | python "$skill_dir/scripts/topic_embed.py"
$topic_sig = ($topic_result | ConvertFrom-Json).signature

# self-persist
$record_topic = @{ mode = "record"; project_dir = $project_root; session_id = $session_id; signature = $topic_sig } | ConvertTo-Json -Compress
$record_topic | python "$skill_dir/scripts/topic_embed.py"
```

---

## Per-Response Pipeline

Run these steps **after generating each response, before displaying it**. Every script that produces metrics self-persists via its `record` mode — you do NOT need to manually write JSON.

### Step 1: Initialise a new turn entry

```powershell
$turn_number = $session.conversation_number
$new_turn_input = @{ mode = "append_new_turn"; project_dir = $project_root; session_id = $session_id; turn = $turn_number } | ConvertTo-Json -Compress
$new_turn_input | python "$skill_dir/scripts/session_store.py"
```

### Step 2: Subjective keyword count (density-normalised)

```powershell
# Count occurrences of each word in $params.keyword_list inside $response
$subjective_count = 0
$matched_keywords = @()
foreach ($kw in $params.keyword_list) {
    $c = [regex]::Matches($response, [regex]::Escape($kw)).Count
    if ($c -gt 0) {
        $subjective_count += $c
        $matched_keywords += $kw
    }
}

# Response tokens (from Step 3 token count)
$response_tokens = ...  # will be set after Step 3
$density = ($subjective_count / [Math]::Max($response_tokens, 1)) * $params.density_multiplier

# self-persist via session_store
$record_kw = @{ mode = "update_last_turn"; project_dir = $project_root; session_id = $session_id; keyword_density = $density; keyword_matches = @($matched_keywords) } | ConvertTo-Json -Compress
$record_kw | python "$skill_dir/scripts/session_store.py"
```

### Step 3: Token count + complexity estimate

```powershell
# Estimate thinking from topic complexity
$comp_input = @{ mode = "estimate"; question = $user_message; topic_sig = $topic_sig; thinking_multiplier = $params.thinking_multiplier } | ConvertTo-Json -Compress
$comp_result = $comp_input | python "$skill_dir/scripts/complexity_estimator.py"
$comp_obj = $comp_result | ConvertFrom-Json
$thinking_est = $comp_obj.estimated_thinking

# Full recount with thinking estimate
# $all_messages should contain the entire conversation history as a single string
$full_input = @{ mode = "full"; text = $all_messages; thinking_estimate = $thinking_est } | ConvertTo-Json -Compress
$full_result = $full_input | python "$skill_dir/scripts/count_tokens.py"
$full_obj = $full_result | ConvertFrom-Json
$cumulative_total = $full_obj.total_tokens
$visible_tokens = $full_obj.visible_tokens

# self-persist
$record_tokens = @{ mode = "record"; project_dir = $project_root; session_id = $session_id; total_tokens = $cumulative_total; visible_tokens = $full_obj.visible_tokens; estimated_thinking = $full_obj.estimated_thinking; thinking_multiplier = $params.thinking_multiplier } | ConvertTo-Json -Compress
$record_tokens | python "$skill_dir/scripts/count_tokens.py"
```

### Step 4: Hash-based char extraction + fuzzy match

```powershell
# Extract chars from current response
$fuzzy_extract = @{ mode = "extract"; text = $response; conv_num = $session.conversation_number; k = $params.k_chars } | ConvertTo-Json -Compress
$chars = (($fuzzy_extract | python "$skill_dir/scripts/fuzzy_match.py") | ConvertFrom-Json).chars

# Compare with previous turn's chars
$prev_chars = $null
if ($turns_data.turns.Count -ge 2) { $prev_chars = $turns_data.turns[-2].fuzzy_chars }

$similarity = 0.0
$fuzzy_score = $null
if ($prev_chars) {
    $fuzzy_compare = @{ mode = "compare"; chars_a = $prev_chars; chars_b = $chars; base = $params.fuzzy_hybrid_base; multiplier = $params.fuzzy_hybrid_multiplier } | ConvertTo-Json -Compress
    $fuzzy_comp_result = $fuzzy_compare | python "$skill_dir/scripts/fuzzy_match.py"
    $fuzzy_obj = $fuzzy_comp_result | ConvertFrom-Json
    $similarity = $fuzzy_obj.similarity
    $fuzzy_score = $fuzzy_obj.fuzzy_score
}

# self-persist
$record_fuzzy = @{ mode = "record"; project_dir = $project_root; session_id = $session_id; chars = $chars; similarity = $similarity; fuzzy_score = $fuzzy_score } | ConvertTo-Json -Compress
$record_fuzzy | python "$skill_dir/scripts/fuzzy_match.py"
```

### Step 5: Decision formula (three-zone)

```powershell
$threshold = $params.threshold

# Redundancy score
$tpi = $params.redundancy_tokens_per_increment
$inc = $params.redundancy_increment
$redundancy_score = ($cumulative_total / $tpi) * $inc

# Formula raw: sum of all signals
$formula_raw = $redundancy_score + ($fuzzy_score ?? 0) + $density

# Three-zone decision
$display_pct = ($formula_raw / [Math]::Max($threshold, 1)) * 100
if ($display_pct -lt 100) {
    $zone = "safe"; $status = "Safe"; $triggered = $false
} elseif ($display_pct -lt 200) {
    $zone = "mark"; $status = "Mark"; $triggered = $true
} else {
    $zone = "verify"; $status = "Verify"; $triggered = $true
}

# self-persist decision result
$record_decision = @{ mode = "update_last_turn"; project_dir = $project_root; session_id = $session_id; phase = $session.phase; redundancy_score = $redundancy_score; formula_raw = $formula_raw; formula_zone = $zone; triggered = $triggered; risk_score = ($formula_raw / [Math]::Max($threshold, 1)) } | ConvertTo-Json -Compress
$record_decision | python "$skill_dir/scripts/session_store.py"
```

### Step 6: Reference material check

```powershell
$material_input = @{ mode = "check"; project_dir = $project_root; session_id = $session_id; current_sig = $topic_sig; threshold = $params.material_collection_threshold } | ConvertTo-Json -Compress
$material_output = $material_input | python "$skill_dir/scripts/reference_material.py"
$material_result = $material_output | ConvertFrom-Json
$material_inconsistency = $material_result.material_inconsistency

# self-persist
$record_material = @{ mode = "record"; project_dir = $project_root; session_id = $session_id; material_inconsistency = $material_inconsistency } | ConvertTo-Json -Compress
$record_material | python "$skill_dir/scripts/reference_material.py"
```

If the user has been on the same topic for 3+ turns, also collect the response as reference material:

```powershell
if ($turns_data.turns.Count -ge 3) {
    $last3 = $turns_data.turns[-3..-1]
    $same_topic = ($last3 | Where-Object { $_.topic_signature }).Count -eq 3
    if ($same_topic) {
        $add_material = @{ mode = "add"; project_dir = $project_root; session_id = $session_id; topic_sig = $topic_sig; claims_text = $response } | ConvertTo-Json -Compress
        $add_material | python "$skill_dir/scripts/reference_material.py"
    }
}
```

### Step 7: Habit profile update

Collect the bin distribution (character positions within response divided into `$params.num_bins` bins), then persist:

```powershell
# bin_counts should be computed by the agent from character positions
# If not available, pass empty array (profile will remain unchanged)
$habit_input = @{ mode = "calc"; bin_counts = $bin_counts } | ConvertTo-Json -Compress
$habit_profile = ($habit_input | python "$skill_dir/scripts/calc_habit.py") | ConvertFrom-Json

$record_habit = @{ mode = "record"; project_dir = $project_root; session_id = $session_id; profile = $habit_profile } | ConvertTo-Json -Compress
$record_habit | python "$skill_dir/scripts/calc_habit.py"
```

### Step 8: Adaptation (periodic)

Run every `$params.adaptation_interval` conversations (default: 10), or when phase transitions to active:

```powershell
if ($session.conversation_number % $params.adaptation_interval -eq 0 -or $session.phase -eq "active") {
    $adapt_input = @{ project_dir = $project_root; skill_dir = $skill_dir; session_id = $session_id } | ConvertTo-Json -Compress
    $adapt_result = $adapt_input | python "$skill_dir/scripts/adapt_threshold.py"
    # adapt_threshold.py reads turns.json internally and writes back
    # reload params
    if (Test-Path $local_params) { $params = Get-Content $local_params -Raw | ConvertFrom-Json }
}
```

### Step 9: Correction (if triggered)

If `$triggered -eq $true` and `$params.correction_enabled -eq $true`:

```powershell
$decide_input = @{ mode = "decide"; history = @{}; params = @{} } | ConvertTo-Json -Compress
$decision = ($decide_input | python "$skill_dir/scripts/correction.py") | ConvertFrom-Json

# ... execute correction logic (Direction A / B) ...

# self-persist correction result
$record_corr = @{ mode = "record"; project_dir = $project_root; session_id = $session_id; method = $decision; correction_applied = $true; claims_extracted = $n; claims_verified = $m; claims_wrong = $k; correction_rate = ($k / [Math]::Max($m, 1)) } | ConvertTo-Json -Compress
$record_corr | python "$skill_dir/scripts/correction.py"
```

### Step 10: Update session.json cumulative counters

```powershell
$session.cumulative.total_tokens = $cumulative_total
$session.cumulative.alert_count = ($turns_data.turns | Where-Object { $_.triggered -eq $true }).Count
$session.cumulative.trigger_count = ($turns_data.turns | Where-Object { $_.formula_zone -eq "verify" }).Count
if ($triggered) { $session.cumulative.correction_count += 1 }
$session | ConvertTo-Json -Depth 10 | Set-Content $session_path
```

---

## Display

Shelter card only on **Mark** or **Verify** status. Silent otherwise.

| Zone | Status | Display |
|------|--------|---------|
| Safe | `Safe` | Nothing |
| Mark | `Mark` | Show shelter card with `display_pct%` and zone label |
| Verify | `Verify` | Show shelter card + correction if applied |

---

## Known Limitations

1. **No ground-truth oracle**: Hallucination probability is estimated via behavioural proxy signals, not verified facts.
2. **Cross-session comparison is topic-gated**: Only compares turns with similar topic signatures (Jaccard >= 0.15).
3. **Baseline assumes honesty**: Early conversations establish a behavioural baseline; if the model hallucinates heavily from turn 1, the threshold adapts to that.
4. **Self-correction is self-referential**: Direction B compares two reasoning paths from the same model, not against an external source.
5. **Monthly Web Fetch budget**: Direction A verification is capped by `web_fetch_monthly_budget`.
6. **Habit profile convergence**: The 5-bin probability distribution requires ~10+ samples before `dominant_bin` becomes meaningful.
7. **Redundancy score scales with conversation length**: Long sessions will see the redundancy signal grow linearly. This is by design but may require manual threshold reset on extremely long sessions.
8. **turns.json grows unbounded**: Each conversation turn appends a full record. For very long sessions (1000+ turns), consider periodic archiving.
9. **No concurrent session support**: Only one active session at a time. Starting a new session while another is running will interleave data.
10. **JSON non-transactional**: If a write fails mid-way, the file may be partially written. The `session_store.py` layer uses atomic read-modify-write but does not guard against power loss.
