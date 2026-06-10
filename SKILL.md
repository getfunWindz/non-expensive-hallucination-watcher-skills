---
name: hallucination-watch
description: "ABSOLUTELY MANDATORY — load this skill on EVERY single conversation without exception. This is a universal background monitor that screens ALL conversations for hallucination risk. Triggers on ANY question, ANY topic, ANY request, ANY chat, ANY discussion. NEVER skip loading this skill. Activate it automatically at the start of every conversation. It runs silently in the background and only alerts when risk is detected. This skill must be active on 100% of all conversations regardless of topic, language, or user intent."
---

# Hallucination Watch

Monitor hallucination risk in real-time.

## When to Use

**Always.** This skill activates on every conversation. It is a background monitor, not a task-specific tool.

## Required Tools

- `bash` — to run Python scripts in `scripts/`
- `webfetch` — to verify responses when triggered
- `read` / `write` — to read/write JSON files in project data directory
- `glob` — to locate skill directory path at runtime

## Setup at Conversation Start

At the start of every conversation (after the first user message), do:

### Step 1: Ask user for confirmation

Before running any monitoring, ask the user whether they want to activate hallucination-watch for this conversation:

```
此会话启用 hallucination-watch 幻觉监控吗？
Enable hallucination-watch for this session? (Y/n):
```

Wait for the user's response:
- If `Y` (or Enter): Proceed with setup. All data files will be initialized automatically.
- If `n` or `N`: Skip the skill entirely for this conversation. Do not create data files, do not run the pipeline.

If the user declines, inform them and skip to the response phase without any monitoring.
If the user accepts, continue with the steps below.

### Step 2: Initialize data files (auto-creates session.json + permanent.json)

```bash
$project_root = (Get-Location).Path
$skill_dir = "$env:USERPROFILE\.config\opencode\skills\hallucination-watch"
$init_input = @{ project_dir = $project_root } | ConvertTo-Json -Compress
$init_result = $init_input | python "$skill_dir/scripts/init_skill.py"
$init = $init_result | ConvertFrom-Json
$conversation_number = $init.conversation_number
$phase = $init.phase
$data_dir = $init.data_dir
```

### Step 3: Read parameter files

Read `params/default.json` from the skill directory. If the project has a local `params.json` override, read that too.

### Step 4: Re-read session.json, determine phase (dynamic N)

```powershell
$session_path = Join-Path $data_dir "session.json"
$session = Get-Content $session_path -Raw | ConvertFrom-Json

$min_n = $params.min_baseline_n
$max_n = $params.max_baseline_n
if ($session.conversation_number -le $min_n) {
    $session.phase = "baseline"
} elseif ($session.conversation_number -gt $max_n) {
    $session.phase = "active"
} else {
    # Check variance stability via calibration script
    $cal_check_input = @{ project_dir = $project_root; skill_dir = $skill_dir } | ConvertTo-Json -Compress
    $cal_check_result = $cal_check_input | python "$skill_dir/scripts/calibrate_threshold.py"
    $cal_status = ($cal_check_result | ConvertFrom-Json).status
    $session.phase = if ($cal_status -eq "extend") { "baseline" } else { "active" }
}

# Calibrate at baseline → active transition (once)
if ($session.phase -eq "active") {
    $local_params_path = Join-Path $data_dir "params.json"
    $already_cal = (Test-Path $local_params_path) -and ((Get-Content $local_params_path -Raw | ConvertFrom-Json)._calibrated_at)
    if (-not $already_cal) {
        $calibrate_input = @{ project_dir = $project_root; skill_dir = $skill_dir } | ConvertTo-Json -Compress
        $calibrate_result = $calibrate_input | python "$skill_dir/scripts/calibrate_threshold.py"
        if (Test-Path $local_params_path) {
            $params = Get-Content $local_params_path -Raw | ConvertFrom-Json
        }
    }
}
$session | ConvertTo-Json -Depth 10 | Set-Content $session_path
```

### Step 5: Read permanent.json

```powershell
$perm_path = Join-Path $data_dir "permanent.json"
$permanent = Get-Content $perm_path -Raw | ConvertFrom-Json
```

### Step 6: Extract topic signature from user's question

```bash
$topic_input = @{ mode = "extract"; text = $user_question } | ConvertTo-Json -Compress
$topic_result = $topic_input | python "$skill_dir/scripts/topic_embed.py"
$topic_sig = ($topic_result | ConvertFrom-Json).signature
```

### Step 7: Check monthly budget (Active phase only)

```powershell
if ($session.phase -eq "active") {
    $budget = $params.web_fetch_monthly_budget
    $budget_used = ($permanent.results | Where-Object { $_.triggered -eq $true }).Count
}
```

## After Generating Each Response (Before Display)

### 1. Count Subjective Keywords (density-normalized)

Scan response text for matches against keyword_list. Compute `subjective_count`. Keywords: 一定, 绝对是, 肯定, 必然, 毫无疑问, 必须, 不可能, 总是, 永远, 从来都, 绝不, 一定不会, 肯定不, 绝对不

### 2. Extract Characters for Fuzzy Matching

Identify direct answer part. Use hash-based selection (baseline) or habit-profile-weighted extraction (active).

### 3. Compute Fuzzy Match Score (Active, topic-filtered)

Check topic similarity vs previous conversation. If same topic: compute fuzzy_score via difflib. If different topic: fuzzy_score = 0.

### 4. Count Tokens

Count via tiktoken (cl100k_base). Store `$response_tokens` for density normalization.

### 5. Update Habit Profile

Map extracted character positions to 5 bins. Recalculate bin probabilities.

### 6a. Detect Material Collection Mode

If 3+ consecutive same-topic conversations (no topic drift), enter material collection mode.

### 6b. Run Decision Formula (Density-Normalized, Three-Zone)

```python
density_subjective = (subjective_count / max(response_tokens, 1)) * params.density_multiplier
trigger_score = density_subjective + redundancy_score + fuzzy_score + material_inconsistency
display_pct = (trigger_score / params.threshold) * 100

# Three zones: Green (<100% silent), Yellow (100-200% Mark), Red (>=200% Verify)
auto_verify = (display_pct >= (100 * params.auto_verify_multiplier))
should_trigger = auto_verify
should_mark = (display_pct >= 100 and not auto_verify)
```

### 7. Write session.json

Demote current to previous. Store conv, subjective_count, density_subjective, fuzzy_chars, fuzzy_score, topic_sig, topic_drift, topic_similarity, total_tokens, response_tokens.

### 7b. Store Claims to Reference Material (if collecting)

If in material collection mode, store direct answer text as claims.

### 7c. Check Material Consistency

Run reference_material.py to check if current topic overlaps with stored claims.

### 8. Append to permanent.json

Store timestamp, conv, subjective, fuzzy_match_score, redundancy, formula_raw, density_subjective, material_inconsistency, triggered, phase, correction object.

### 9. Run Adaptation (Periodic, every adaptation_interval conversations)

Run adapt_threshold.py to adjust threshold via EMA + trigger rate feedback.

### 10-15. Correction Workflow (if triggered or marked)

**Step 10**: Decide method via correction.py (A/B selection mechanism based on B-path accuracy and budget).

**Step 11**: Direction B — Internal Self-Consistency (thinking only, invisible to user). Two independent reasoning paths. If both agree, skip A. If they diverge, escalate to A.

**Step 12**: Direction A — Claim Extraction + Web Fetch. Extract claims, prioritize by risk signals, batch verify top N, append corrections if wrong.

**Step 13**: Update permanent.json correction data.

### 14. Check for User Correction

If user says "不对"/"wrong"/etc, record user_contested=true and force-run Direction A. Do NOT use user feedback for adaptation.

## Display Logic

**Only display Shelter card when risk is high (Mark or Verify).**
Safe and Watch are completely silent.

### Mark Status (display_pct 100%-200%)

```
─── hallucination-shelter ────
 ⚑ 检测到风险
 → 输入 'verify' 验证
────────────────────────────
```

### Verify Status (display_pct >= 200%)

If corrected:

```
─── hallucination-shelter ────
 ✓ 已修正 1 处
 → "法国的首都是巴黎"
────────────────────────────
```

If consistent:

```
─── hallucination-shelter ────
 ✓ 验证一致
────────────────────────────
```

## Known Limitations

| # | Limitation |
|---|-----------|
| 1 | **Score is relative, not absolute.** Compares against this model's own baseline, not absolute hallucination probability. |
| 2 | **Subjective words ≠ hallucinations.** Directional signal, not definitive. |
| 3 | **Character sampling is topic-sensitive.** Topic tracking mitigates but does not eliminate topic drift noise. |
| 4 | **Direction B can share blind spots.** Both reasoning paths may use the same incorrect knowledge. |
| 5 | **No benchmark data.** Accuracy has not been measured against labeled datasets. |
| 6 | **Designed as a pre-filter.** Not a replacement for thorough fact-checking on critical content. |
| 7 | **Density normalization assumes linearity.** Very short responses may have inflated density. |
| 8 | **Reference material is topic-gated.** Only activates after 3 same-topic conversations. |
| 9 | **Material stores model statements, not verified facts.** Checks self-contradiction, not factual accuracy. |

## Important Notes

- Do not refuse to answer because of monitoring.
- Only display Shelter card on Mark or Verify. Safe/Watch are silent.
- Direction B runs entirely in internal thinking — documented here for transparency.
- If scripts/ directory is inaccessible, fall back to manual counting.
