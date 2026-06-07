---
name: hallucination-watch
description: "Low-cost hallucination risk screening for every conversation. Uses behavioral proxy signals (subjective keywords, cross-session consistency) to estimate risk without expensive external calls. Only displays alerts when risk exceeds threshold. Automatically verifies and corrects when risk is high. Use in EVERY conversation as a first-pass risk filter — activates in background, stays silent unless needed."
---

# Hallucination Watch

Monitor hallucination risk in real-time. At the end of EVERY response, compute and display:

```
─── Metrics ──────────────────────
 Input: 1,247 | Output: 896 | Total: 2,143
 Subjective: 3 | FuzzyDiff: 72% | Redundancy: 0
 Hallucination Score: ░░░░░░ 0.0075% | Threshold: 100%
─────────────────────────────────
```

## When to Use

**Always.** This skill activates on every conversation. It is a background monitor, not a task-specific tool.

## Required Tools

- `bash` — to run Python scripts in `scripts/`
- `webfetch` — to verify responses when triggered
- `read` / `write` — to read/write JSON files in project data directory
- `glob` — to locate skill directory path at runtime

## Setup at Conversation Start

At the start of every conversation (after the first user message), do:

### Step 1: Ensure data directory exists

```bash
$project_root = (Get-Location).Path
$skill_dir = "$env:USERPROFILE\.config\opencode\skills\hallucination-watch"
$data_dir = Join-Path $project_root "hallucination-watch"
if (-not (Test-Path $data_dir)) { New-Item -ItemType Directory -Path $data_dir -Force }
```

### Step 2: Read parameter files

Read `params/default.json` from the skill directory. If the project has a local `params.json` override, read that too (it overrides default.json values).

### Step 3: Read or initialize session.json

```powershell
$session_path = Join-Path $data_dir "session.json"
$session = if (Test-Path $session_path) {
    Get-Content $session_path | ConvertFrom-Json
} else {
    @{
        conversation_number = 0
        phase = "baseline"
        previous = $null
        current = $null
        habit_profile = @{
            total_samples = 0
            bin_probs = @(0.2, 0.2, 0.2, 0.2, 0.2)
            dominant_bin = $null
        }
    }
}
$session.conversation_number += 1

# Determine phase (dynamic N)
$min_n = $params.min_baseline_n
$max_n = $params.max_baseline_n
if ($session.conversation_number -le $min_n) {
    $session.phase = "baseline"
} elseif ($session.conversation_number -gt $max_n) {
    $session.phase = "active"  # Force transition after max_n
} else {
    # Check variance stability via calibration script
    $cal_check_input = @{ project_dir = (Get-Location).Path; skill_dir = $skill_dir } | ConvertTo-Json -Compress
    $cal_check_result = $cal_check_input | python "$skill_dir/scripts/calibrate_threshold.py"
    $cal_status = ($cal_check_result | ConvertFrom-Json).status
    if ($cal_status -eq "extend") {
        $session.phase = "baseline"  # Need more data
    } else {
        $session.phase = "active"  # Variance stable or forced
    }
}

# Calibrate threshold at baseline → active transition (once)
if ($session.phase -eq "active") {
    $local_params_path = Join-Path $data_dir "params.json"
    $already_calibrated = (Test-Path $local_params_path) -and ((Get-Content $local_params_path -Raw | ConvertFrom-Json)._calibrated_at)
    if (-not $already_calibrated) {
        $calibrate_input = @{ project_dir = (Get-Location).Path; skill_dir = $skill_dir } | ConvertTo-Json -Compress
        $calibrate_result = $calibrate_input | python "$skill_dir/scripts/calibrate_threshold.py"
        if (Test-Path $local_params_path) {
            $params = Get-Content $local_params_path -Raw | ConvertFrom-Json
        }
    }
}
```

### Step 4: Read permanent.json

```powershell
$perm_path = Join-Path $data_dir "permanent.json"
$permanent = if (Test-Path $perm_path) {
    Get-Content $perm_path | ConvertFrom-Json
} else {
    @{ last_updated = $null; results = @() }
}
```

### Step 5: Extract topic signature from user's question

```bash
$topic_input = @{ mode = "extract"; text = $user_question } | ConvertTo-Json -Compress
$topic_result = $topic_input | python "$skill_dir/scripts/topic_embed.py"
$topic_sig = ($topic_result | ConvertFrom-Json).signature
```

### Step 6: Check monthly budget (Active phase only)

```powershell
if ($session.phase -eq "active") {
    $budget = $params.web_fetch_monthly_budget
    $budget_used = ($permanent.results | Where-Object { $_.triggered -eq $true }).Count
    $budget_remaining = $budget - $budget_used
}
```

## After Generating Each Response (Before Display)

After you generate a response but before showing it to the user, execute this pipeline:

### 1. Count Subjective Keywords

Scan your response text for matches against `params.keyword_list`. Count each match and compute `subjective_count`.

Keywords: `一定`, `绝对是`, `肯定`, `必然`, `毫无疑问`, `必须`, `不可能`, `总是`, `永远`, `从来都`, `绝不`, `一定不会`, `肯定不`, `绝对不`

### 2. Extract Characters for Fuzzy Matching

Identify the part of your response that **directly answers the user's question**. From that part, extract characters.

**Baseline phase** — use uniform hash-based selection
**Active phase** — use habit-profile-weighted extraction

### 3. Compute Fuzzy Match Score (Active Phase Only)

First check topic similarity. If same topic, compute fuzzy score. If different topic, fuzzy_score = 0.

### 4. Count Tokens

Count tokens via tiktoken, store `$response_tokens` for density normalization.

### 5. Update Habit Profile

Map each extracted character's position to a bin, update profile probabilities.

### 6a. Detect Material Collection Mode

After 3+ consecutive same-topic conversations, enter material collection mode.

### 6b. Run Decision Formula

```python
density_subjective = (subjective_count / max(response_tokens, 1)) * 1000
trigger_score = density_subjective + redundancy_score + fuzzy_score + material_inconsistency
display_pct = (trigger_score / params.threshold) * 100
```

### 7. Write session.json
### 7b. Store Claims to Reference Material
### 7c. Check Material Consistency
### 8. Append to permanent.json
### 9. Run Adaptation (Periodic)
### 10-13. Correction Workflow (Direction B + Direction A)
### 14. Check for User Correction

## Display Logic

Shelter card only shown on Mark or Verify status.

## Known Limitations

9 documented limitations covering score relativity, signal directionality, topic sensitivity, B-path blind spots, missing benchmarks, density assumptions, and material anchoring constraints.