"""
calibrate_threshold.py — Baseline calibration reading from turns.json.

Reads: {project}/hallucination-watch/sessions/{session_id}/turns.json
       → turns[].formula_raw (phase == "baseline")

Calibrates the detection threshold at the baseline→active transition.
"""
import json
import sys
from pathlib import Path


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except json.JSONDecodeError:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    d = json.loads(sys.stdin.read())
    proj, skill = d["project_dir"], d["skill_dir"]
    sid = d["session_id"]

    params_path = Path(proj) / "hallucination-watch" / "params.json"
    if params_path.exists():
        params = load_json(params_path)
    else:
        params = load_json(Path(skill) / "params" / "default.json")

    min_n = params.get("min_baseline_n", 6)
    max_n = params.get("max_baseline_n", 20)
    cv_th = params.get("variance_stable_threshold", 0.3)
    mult = params.get("calibration_multiplier", 3.0)
    min_t = params.get("min_calibrated_threshold", 100)

    # ── read turns.json instead of permanent.json ──────────────────
    from session_store import get_turns_by_phase

    turns = get_turns_by_phase(proj, sid, "baseline")
    raws = [t["formula_raw"] for t in turns if "formula_raw" in t]
    n = len(raws)

    if n < min_n:
        print(json.dumps({
            "status": "skipped", "n": n,
            "reason": f"only {n} baseline formula_raw records (need {min_n})",
        }))
        return

    mean = sum(raws) / n
    std = (sum((r - mean) ** 2 for r in raws) / n) ** 0.5
    cv = std / mean if mean > 0 else 0.0

    if n >= max_n:
        status = "forced"
    elif cv <= cv_th:
        status = "calibrated"
    else:
        print(json.dumps({
            "status": "extend", "n": n, "mean": round(mean, 2),
            "std": round(std, 2), "cv": round(cv, 4),
        }))
        return

    threshold = max(mean + mult * std, float(min_t))
    existing = load_json(params_path) if params_path.exists() else {}
    existing["threshold"] = round(threshold, 2)
    existing["_calibrated_at"] = True
    existing["_calibration_mean"] = round(mean, 2)
    existing["_calibration_std"] = round(std, 2)
    existing["_calibration_n"] = n
    save_json(params_path, existing)

    print(json.dumps({
        "status": status, "mean": round(mean, 2), "std": round(std, 2),
        "n": n, "new_threshold": round(threshold, 2),
    }))


if __name__ == "__main__":
    main()
