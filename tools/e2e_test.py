"""
End-to-end test for hallucination-watch v3.0.

Tests:
  - Baseline phase (6 convs) — no triggers, safe status
  - Active phase (14 convs) — moderate scores, watch status
  - Trigger phase (10 convs) — formula triggers, correction activates
  - Correction: Direction B internal consistency (simulated)
  - Correction: Direction A claim extraction + prioritize
  - Selection mechanism: first_trigger, b_reliable, budget_saving
  - Adaptation layer with correction feedback
  - turns.json correction field integrity
  - params.json threshold adjustments
"""
import json
import hashlib
import difflib
import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime, timezone

SKILL_DIR = Path(os.environ["USERPROFILE"]) / ".config" / "opencode" / "skills" / "hallucination-watch"
TEST_DIR = Path(os.environ["TEMP"]) / "hallucination-watch-e2e"
DATA_DIR = TEST_DIR / "hallucination-watch"

# ── Comprehensive test data (50 conversations) ──
# (conv, user_msg, model_response, is_baseline)
CONVERSATIONS = []

# Phase 1: Baseline (1-6) — safe, no triggers
BASELINE_CONVS = [
    (1, "What is the capital of China?", "北京的中国的首都。"),
    (2, "What is 2+2?", "2+2等于4。"),
    (3, "What is the tallest mountain?", "珠穆朗玛峰是世界上最高的山峰。"),
    (4, "Who wrote Hamlet?", "哈姆雷特是莎士比亚写的。"),
    (5, "What is the speed of light?", "光速大概是每秒299792458米。"),
    (6, "Is the Earth round?", "地球是圆的。"),
]
for c, u, r in BASELINE_CONVS:
    CONVERSATIONS.append((c, u, r, True))

# Phase 2: Active — moderate scores (7-20)
ACTIVE_MODERATE = [
    (7, "Capital of France?", "法国的首都是巴黎。"),
    (8, "What is Python?", "Python是一种编程语言。"),
    (9, "Define gravity", "重力是物体之间的吸引力。"),
    (10, "Who discovered penicillin?", "青霉素是弗莱明发现的。"),
    (11, "Capital of Japan?", "日本的首都是东京。"),
    (12, "What is AI?", "AI是人工智能。"),
    (13, "Capital of Australia?", "澳大利亚的首都是堪培拉。"),
    (14, "What is DNA?", "DNA是脱氧核糖核酸。"),
    (15, "Capital of Egypt?", "埃及的开罗是首都。"),
    (16, "What is relativity?", "相对论是爱因斯坦提出的。"),
    (17, "Capital of Brazil?", "巴西的首都是巴西利亚。"),
    (18, "What is entropy?", "熵是系统的混乱程度。"),
    (19, "Capital of Canada?", "加拿大的首都是渥太华。"),
    (20, "Define photosynthesis", "光合作用是植物利用光能的过程。"),
]
for c, u, r in ACTIVE_MODERATE:
    CONVERSATIONS.append((c, u, r, False))

# Phase 3: Trigger phase (21-30) — high subjective + high fuzzy → triggers
TRIGGER_CONVS = [
    (21, "What is the capital of China?", "中国的首都是北京，绝对是毋庸置疑的。"),
    (22, "Distance to the moon?", "月球距离地球一定是384400公里，这是毫无疑问的。"),
    (23, "Who invented the telephone?", "电话绝对是贝尔发明的，这一点毫无疑问。"),
    (24, "Population of Tokyo?", "东京人口绝对是1392万以上。"),
    (25, "Speed of sound?", "声速一定是每秒343米，不可能有错。"),
    (26, "What is E=mc2?", "质能方程绝对是爱因斯坦提出的，从来都没有争议。"),
    (27, "Who was first on the moon?", "第一个登上月球的绝对是阿姆斯特朗。"),
    (28, "Capital of UK?", "英国首都是伦敦，必然是这个答案。"),
    (29, "What is pH of water?", "纯水的pH肯定是7，毫无疑问。"),
    (30, "Define black hole?", "黑洞一定是引力极强的天体，连光都无法逃脱，绝对没错。"),
]
for c, u, r in TRIGGER_CONVS:
    CONVERSATIONS.append((c, u, r, False))

# Phase 4: Correction phase (31-40) — triggers + correction scenarios
CORRECTION_CONVS = [
    (31, "Capital of France?", "法国的首都是巴黎。"),
    (32, "What is the largest planet?", "木星绝对是太阳系最大的行星。"),
    (33, "Capital of Argentina?", "阿根廷的首都是布宜诺斯艾利斯的。"),
    (34, "Define algorithm", "算法是一系列解决问题的步骤，肯定是这样定义的。"),
    (35, "Capital of Norway?", "挪威的首都是奥斯陆。"),
    (36, "What is gravity?", "重力的大小一定与质量和距离有关，这是确定的。"),
    (37, "Capital of New Zealand?", "新西兰的首都是惠灵顿。"),
    (38, "Define momentum", "动量绝对是质量和速度的乘积。"),
    (39, "Capital of South Korea?", "韩国的首都是首尔。"),
    (40, "What is a black swan event?", "黑天鹅事件绝对是不可预测的罕见事件。"),
]
for c, u, r in CORRECTION_CONVS:
    CONVERSATIONS.append((c, u, r, False))

# Phase 5: Budget test (41-50) — high token usage to test B-only
BUDGET_CONVS = [
    (41, "What is quantum mechanics? A very long question here...", "量子力学是描述微观世界的物理理论。"),
    (42, "Explain the theory of evolution in detail with examples...", "进化论是物种通过自然选择逐渐演化的过程。"),
    (43, "What is the history of the Roman Empire? Beginning...", "罗马帝国起源于公元前27年。"),
    (44, "Describe the structure of a cell and its organelles...", "细胞是生命的基本单位，由细胞膜、细胞质和细胞核组成。"),
    (45, "Explain the process of protein synthesis step by step...", "蛋白质合成包括转录和翻译两个主要步骤。"),
]
for c, u, r in BUDGET_CONVS:
    CONVERSATIONS.append((c, u, r, False))
# Repeat a few to reach 50
for i in range(46, 51):
    CONVERSATIONS.append((i, "Tell me something interesting.", "这个世界充满了有趣的知识，绝对没错。", False))


# ── End of test data ──

TRIGGER_HISTORY = []  # Tracks which convs triggered for correction simulation


def setup():
    if TEST_DIR.exists():
        import shutil
        shutil.rmtree(TEST_DIR)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[SETUP] Test directory: {TEST_DIR}")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_default_params():
    return load_json(SKILL_DIR / "params" / "default.json")


def count_subjective(text, keywords):
    return sum(text.count(kw) for kw in keywords)


def extract_chars(text, conv_num, k=5):
    if not text:
        return ""
    seed = f"{text}{conv_num}"
    h = hashlib.sha256(seed.encode()).hexdigest()
    positions = [int(h[i*8:(i+1)*8], 16) % max(len(text), 1) for i in range(k)]
    return "".join(text[p] for p in sorted(positions))


def calc_bins(text, chars):
    if not text or not chars:
        return []
    bins = []
    for ch in chars:
        pos = text.find(ch)
        if pos >= 0:
            bin_idx = min(pos * 5 // max(len(text), 1), 4)
            bins.append(bin_idx)
    return bins


def run_fuzzy_compare(chars_a, chars_b):
    if not chars_a or not chars_b:
        return {"similarity": 0, "similarity_pct": 0, "fuzzy_score": 0}
    sim = difflib.SequenceMatcher(None, chars_a, chars_b).ratio()
    sim_pct = sim * 100
    fuzzy_score = 0 if sim_pct >= 80 else max(50, (100 - sim_pct) * 2.5)
    return {
        "similarity": round(sim, 4),
        "similarity_pct": round(sim_pct, 2),
        "fuzzy_score": round(fuzzy_score, 2)
    }


def simulate_direction_b(conv_num, should_trigger, is_first):
    """Simulate Direction B: internal self-consistency check.

    Returns: (b_path_agreed: bool, method: str)
    """
    global TRIGGER_HISTORY

    if not should_trigger:
        return {
            "method": "none",
            "b_path_agreed": None,
            "claims_extracted": 0,
            "claims_verified": 0,
            "claims_wrong": 0,
            "correction_applied": False
        }

    b_path_agreed = True
    method = "none"

    decision_input = json.dumps({
        "mode": "decide",
        "history": {
            "correction_method": "existing" if TRIGGER_HISTORY else None,
            "b_path_accuracy": _calc_b_accuracy()
        },
        "params": {
            "b_path_min_accuracy": 0.8,
            "token_usage_pct": min(conv_num * 2.5, 100)
        }
    })
    import subprocess
    proc = subprocess.run(
        ["python", str(SKILL_DIR / "scripts" / "correction.py")],
        input=decision_input, capture_output=True, text=True
    )
    decision = json.loads(proc.stdout.strip())

    use_b = decision["use_b"]
    use_a = decision["use_a"]

    if use_b:
        # Simulate B path: for trigger convs, random agreement
        b_path_agreed = (conv_num % 5 != 0)  # 80% agreement rate
        method = "B"

    if use_a:
        # Simulate Direction A: extract claims, prioritize, verify
        method = "A+B" if use_b else "A"

        # Simulate claim extraction
        simulated_claims = [
            {"text": "巴黎是法国的首都", "position": 5, "subjective_positions": [], "fuzzy_score": 0},
            {"text": "月球距离地球384400公里", "position": 10, "subjective_positions": [8], "fuzzy_score": 50},
            {"text": "爱因斯坦提出了相对论", "position": 15, "subjective_positions": [12], "fuzzy_score": 100},
        ]

        # Prioritize via correction.py
        prioritize_input = json.dumps({
            "mode": "prioritize",
            "claims": simulated_claims,
            "max_claims": 3
        })
        proc2 = subprocess.run(
            ["python", str(SKILL_DIR / "scripts" / "correction.py")],
            input=prioritize_input, capture_output=True, text=True
        )
        prioritize_result = json.loads(proc2.stdout.strip())
        top_claims = prioritize_result["selected"]

        # Simulate verification: 1 out of 3 claims is wrong on convs 25+
        corrections = []
        for claim in top_claims:
            is_wrong = (conv_num >= 25 and "爱因斯坦" in claim["text"])
            if is_wrong:
                corrections.append({
                    "original_claim": claim["text"],
                    "verified_fact": "阿尔伯特·爱因斯坦提出了相对论"
                })

        claims_extracted = len(top_claims)
        claims_verified = len(top_claims)
        claims_wrong = len(corrections)
        correction_applied = len(corrections) > 0
    else:
        # B only
        claims_extracted = 0
        claims_verified = 0
        claims_wrong = 0
        correction_applied = False

    TRIGGER_HISTORY.append({
        "conv": conv_num,
        "method": method,
        "b_path_agreed": b_path_agreed if use_b else None,
        "claims_wrong": claims_wrong if use_a else 0,
        "correction_applied": correction_applied
    })

    return {
        "method": method,
        "b_path_agreed": b_path_agreed,
        "claims_extracted": claims_extracted,
        "claims_verified": claims_verified,
        "claims_wrong": claims_wrong,
        "correction_applied": correction_applied
    }


def _calc_b_accuracy():
    """Calculate historical B-path accuracy from trigger history."""
    if not TRIGGER_HISTORY:
        return 0.5
    b_entries = [h for h in TRIGGER_HISTORY if h.get("b_path_agreed") is not None]
    if not b_entries:
        return 0.5
    agreed = sum(1 for h in b_entries if h["b_path_agreed"])
    return agreed / len(b_entries)


def simulate_conversation(conv_num, user_msg, model_response, is_baseline,
                          session, params, permanent):
    subjective_count = count_subjective(model_response, params["keyword_list"])
    direct_answer = model_response
    current_chars = extract_chars(direct_answer, conv_num, params["k_chars"])

    fuzzy_score = 0
    fuzzy_compare_result = None
    if not is_baseline and session.get("previous") and session["previous"].get("fuzzy_chars"):
        prev_chars = session["previous"]["fuzzy_chars"]
        fuzzy_compare_result = run_fuzzy_compare(prev_chars, current_chars)
        fuzzy_score = fuzzy_compare_result["fuzzy_score"]

    total_tokens = len(user_msg + model_response)
    redundancy_score = 0

    # Habit profile
    bins = calc_bins(model_response, current_chars)
    hp = session.get("habit_profile", {"total_samples": 0, "bin_probs": [0.2] * 5})
    if bins:
        hp["total_samples"] = hp.get("total_samples", 0) + len(bins)
        hp.setdefault("bin_counts", [0] * 5)
        for b in bins:
            hp["bin_counts"][b] = hp["bin_counts"][b] + 1
        total = sum(hp["bin_counts"])
        if total > 0:
            hp["bin_probs"] = [round(c / total, 4) for c in hp["bin_counts"]]
        hp["dominant_bin"] = hp["bin_probs"].index(max(hp["bin_probs"]))
    session["habit_profile"] = hp

    # Decision formula
    trigger_score = subjective_count + redundancy_score + fuzzy_score
    should_trigger = (trigger_score - params["threshold"]) >= 0
    display_pct = min((trigger_score / params["threshold"]) * 100, 100) if params["threshold"] > 0 else 0
    status = "Safe"
    if not is_baseline:
        if display_pct >= 1 and display_pct < 100:
            status = "Watch"
        elif display_pct >= 100:
            status = "Verify"

    # Correction layer (v3.0)
    correction_result = simulate_direction_b(conv_num, should_trigger,
                                              not TRIGGER_HISTORY)

    correction_data = correction_result

    # Write session.json
    session["previous"] = session.get("current")
    session["current"] = {
        "conv": conv_num,
        "subjective_count": subjective_count,
        "fuzzy_chars": current_chars,
        "fuzzy_score": fuzzy_score,
        "total_tokens": total_tokens,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    session["conversation_number"] = conv_num
    session["phase"] = "baseline" if is_baseline else "active"
    save_json(DATA_DIR / "session.json", session)

    # Append to turns.json
    turns_path = DATA_DIR / "sessions" / "e2e-test" / "turns.json"
    if turns_path.exists():
        turns_data = load_json(turns_path)
    else:
        turns_data = {"turns": []}
    turn_entry = {
        "turn": conv_num,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": "baseline" if is_baseline else "active",
        "keyword_density": 0.0,
        "keyword_matches": [],
        "fuzzy_chars": current_chars,
        "fuzzy_similarity": fuzzy_compare_result["similarity"] if fuzzy_compare_result else None,
        "fuzzy_score": fuzzy_score,
        "total_tokens": total_tokens,
        "visible_tokens": total_tokens,
        "estimated_thinking": 0,
        "redundancy_score": redundancy_score,
        "material_inconsistency": 0,
        "formula_raw": trigger_score,
        "formula_zone": "safe" if status == "Safe" else "watch" if status == "Watch" else "verify",
        "triggered": should_trigger,
        "risk_score": display_pct / 100.0,
        "correction": correction_data
    }
    turns_data["turns"].append(turn_entry)
    turns_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(turns_path, turns_data)

    # Print summary (compact, no garbled chars)
    fuzz_str = f"{fuzzy_compare_result['similarity_pct']}%" if fuzzy_compare_result else "N/A"
    corr_str = correction_data['method']
    wrong_str = f" ({correction_data['claims_wrong']} wrong)" if correction_data.get('claims_wrong') else ""
    corr_note = f" [{corr_str}{wrong_str}]" if corr_str != "none" else ""

    phase_str = "BASELINE" if is_baseline else "ACTIVE"
    print(f"[CONV #{conv_num:02d}] {phase_str:8s} | Subj:{subjective_count} Fuzzy:{fuzz_str:5s} "
          f"Score:{trigger_score:5.0f} Thresh:{params['threshold']:8.0f} "
          f"Risk:{display_pct:6.2f}% Status:{status:6s}{corr_note}")

    return session, permanent


def run_adaptation(conv_num, params):
    turns_path = DATA_DIR / "sessions" / "e2e-test" / "turns.json"
    if turns_path.exists():
        turns_data = load_json(turns_path)
        results = [r for r in turns_data.get("turns", []) if r.get("phase") == "active"]
    else:
        results = []
    if not results:
        return params

    total = len(results)
    triggered = sum(1 for r in results if r.get("triggered", False))
    current_rate = triggered / total if total > 0 else 0

    # Count corrections (v3.0 signal)
    corrections = sum(1 for r in results
                      if r.get("correction", {}).get("correction_applied"))
    correction_rate = corrections / max(triggered, 1)

    target_rate = params.get("target_trigger_rate", 0.10)
    margin = params.get("rate_margin", 0.02)
    inc_factor = params.get("threshold_increase_factor", 1.10)
    dec_factor = params.get("threshold_decrease_factor", 0.90)
    alpha = params.get("ema_alpha", 0.3)

    threshold = float(params["threshold"])
    old_threshold = threshold

    # Stage 1: Trigger rate feedback
    if current_rate > target_rate + margin:
        threshold *= inc_factor
        reason = f"rate {current_rate:.1%} > {target_rate+margin:.0%}"
    elif current_rate < target_rate - margin:
        threshold *= dec_factor
        reason = f"rate {current_rate:.1%} < {target_rate-margin:.0%}"
    else:
        reason = f"rate {current_rate:.1%} OK"

    # Stage 2: EMA pull
    formula_raws = [r.get("formula_raw", 0) for r in results[-20:]]
    ema_adjusted = False
    if formula_raws:
        ema = float(formula_raws[0])
        for v in formula_raws[1:]:
            ema = alpha * ema + (1 - alpha) * float(v)
        if ema > 0 and threshold / ema > 100:
            threshold = ema * 50
            ema_adjusted = True

    threshold = max(threshold, 1.0)

    print(f"  [ADAPT #{conv_num:02d}] {old_threshold:.0f} -> {threshold:.0f} "
          f"({reason}{', EMA' if ema_adjusted else ''}) "
          f"Trigger:{current_rate:.1%} CorrRate:{correction_rate:.0%}")

    params["threshold"] = round(threshold, 2)
    save_json(DATA_DIR / "params.json", params)
    return params


def main():
    setup()
    params = load_default_params()
    baseline_n = params.get("min_baseline_n", 6)
    adapt_interval = params["adaptation_interval"]

    # Calibration will be called at conv #7 (baseline → active transition)
    # For now, keep the 1M default; calibration will replace it
    calibration_done = False

    session = {
        "conversation_number": 0,
        "phase": "baseline",
        "previous": None,
        "current": None,
        "habit_profile": {"total_samples": 0, "bin_probs": [0.2] * 5}
    }
    permanent = {"last_updated": None, "results": []}

    print(f"\n{'='*60}")
    print(f" v3.0 E2E TEST")
    print(f" Baseline: {baseline_n} | Adapt interval: {adapt_interval}")
    print(f" Total conversations: {len(CONVERSATIONS)}")
    print(f"{'='*60}\n")

    # Run conversations
    for conv_num, user_msg, model_response, is_baseline in CONVERSATIONS:
        # Calibrate at baseline → active transition (before first active conv)
        if not is_baseline and not calibration_done:
            calib_input = json.dumps({
                "project_dir": str(TEST_DIR),
                "skill_dir": str(SKILL_DIR)
            })
            calib_result = json.loads(
                subprocess.run(
                    ["python", str(SKILL_DIR / "scripts" / "calibrate_threshold.py")],
                    input=calib_input, capture_output=True, text=True
                ).stdout.strip()
            )
            calibration_done = True
            # Merge calibrated threshold into existing params (don't replace full config)
            local_params_path = DATA_DIR / "params.json"
            if local_params_path.exists():
                calib_data = load_json(local_params_path)
                params["threshold"] = calib_data["threshold"]
            print(f"  [CALIBRATE] mean={calib_result['mean']} std={calib_result['std']} "
                  f"→ threshold={calib_result['new_threshold']}")

        session, permanent = simulate_conversation(
            conv_num, user_msg, model_response, is_baseline,
            session, params, permanent
        )

        if not is_baseline and conv_num % adapt_interval == 0:
            params = run_adaptation(conv_num, params)

    # ── Final Verification ──
    print(f"\n{'='*60}")
    print(" FINAL VERIFICATION")
    print(f"{'='*60}")

    session_check = load_json(DATA_DIR / "session.json")
    turns_check = load_json(DATA_DIR / "sessions" / "e2e-test" / "turns.json")

    results = turns_check.get("turns", [])
    baseline_r = [r for r in results if r["phase"] == "baseline"]
    active_r = [r for r in results if r["phase"] == "active"]
    triggered_r = [r for r in results if r.get("triggered")]
    corrected_r = [r for r in results
                   if r.get("correction", {}).get("correction_applied")]

    # Check correction method distribution
    methods = {}
    for r in results:
        m = r.get("correction", {}).get("method", "none")
        methods[m] = methods.get(m, 0) + 1

    # Verify no corrupt data
    all_valid = all(
        isinstance(r.get("turn"), int) and
        r.get("phase") in ("baseline", "active") and
        isinstance(r.get("correction"), dict)
        for r in results
    )

    print(f"\n Records: {len(results)} total")
    print(f"   Baseline: {len(baseline_r)} | Active: {len(active_r)}")
    print(f"   Triggered: {len(triggered_r)} | Corrected: {len(corrected_r)}")
    print(f"   Correction methods: {methods}")
    print(f"   All records valid: {'PASS' if all_valid else 'FAIL'}")

    # Verify correction data integrity
    corr_fields_valid = all(
        all(k in r.get("correction", {}) for k in
            ("method", "b_path_agreed", "claims_extracted",
             "claims_verified", "claims_wrong", "correction_applied"))
        for r in active_r
    )
    print(f"   Correction fields complete: {'PASS' if corr_fields_valid else 'FAIL'}")

    hp = session_check.get("habit_profile", {})
    print(f"   Habit profile bins: {[round(p,3) for p in hp.get('bin_probs', [])]}")
    print(f"   Dominant bin: {hp.get('dominant_bin')}")

    # Verify params.json was created and updated
    params_path = DATA_DIR / "params.json"
    if params_path.exists():
        pcheck = load_json(params_path)
        differed = pcheck["threshold"] != load_default_params()["threshold"]
        calibrated = pcheck.get("_calibrated_at", False)
        print(f"   params.json threshold: {pcheck['threshold']}")
        print(f"   Threshold changed from default: {'YES' if differed else 'NO'}")
        print(f"   Calibration applied: {'YES' if calibrated else 'NO'}")
        if calibrated:
            print(f"     mean={pcheck['_calibration_mean']} "
                  f"std={pcheck['_calibration_std']} "
                  f"n={pcheck['_calibration_n']}")
    else:
        print(f"   params.json: MISSING — FAIL")

    # Overall pass/fail
    checks = [
        ("Total records >= 50", len(results) >= 50),
        ("Baseline records == 6", len(baseline_r) == 6),
        ("Some triggers occurred", len(triggered_r) > 0),
        ("Some corrections applied", len(corrected_r) > 0),
        ("Multiple correction methods used", len(methods) > 1),
        ("All records valid", all_valid),
        ("Correction fields complete", corr_fields_valid),
        ("Adaptation ran (params.json exists)", params_path.exists()),
    ]

    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    print(f"\n {'='*50}")
    for label, ok in checks:
        print(f"   {'PASS' if ok else 'FAIL'}: {label}")
    print(f" {'='*50}")
    print(f" {passed}/{total} checks passed")
    print(f" {'='*50}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
