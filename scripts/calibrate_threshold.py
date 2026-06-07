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

def load_params(skill_dir, project_dir):
    local_path = Path(project_dir) / "hallucination-watch" / "params.json"
    if local_path.exists():
        return load_json(local_path)
    return load_json(Path(skill_dir) / "params" / "default.json")

def main():
    data = json.loads(sys.stdin.read())
    project_dir, skill_dir = data["project_dir"], data["skill_dir"]
    params = load_params(skill_dir, project_dir)
    min_n = params.get("min_baseline_n", 6)
    max_n = params.get("max_baseline_n", 20)
    cv_threshold = params.get("variance_stable_threshold", 0.3)
    multiplier = params.get("calibration_multiplier", 3.0)
    min_threshold = params.get("min_calibrated_threshold", 100)

    perm_path = Path(project_dir) / "hallucination-watch" / "permanent.json"
    if not perm_path.exists():
        print(json.dumps({"status":"skipped","n":0,"reason":"no permanent.json"}))
        return
    permanent = load_json(perm_path)
    baseline_raws = [r["formula_raw"] for r in permanent.get("results",[]) if r.get("phase")=="baseline" and "formula_raw" in r]
    n = len(baseline_raws)
    if n < min_n:
        print(json.dumps({"status":"skipped","n":n,"reason":f"only {n} records"}))
        return
    mean = sum(baseline_raws) / n
    variance = sum((r-mean)**2 for r in baseline_raws) / n
    std = variance**0.5
    cv = std/mean if mean>0 else 0.0
    if n >= max_n:
        status = "forced"
    elif cv <= cv_threshold:
        status = "calibrated"
    else:
        print(json.dumps({"status":"extend","n":n,"mean":round(mean,2),"std":round(std,2),"cv":round(cv,4),"reason":f"CV={cv:.3f}>{cv_threshold}"}))
        return
    threshold = max(mean + multiplier * std, float(min_threshold))
    params_path = Path(project_dir) / "hallucination-watch" / "params.json"
    existing = load_json(params_path) if params_path.exists() else {}
    existing.update({"threshold":round(threshold,2),"_calibrated_at":True,"_calibration_mean":round(mean,2),"_calibration_std":round(std,2),"_calibration_n":n,"_calibration_status":status})
    save_json(params_path, existing)
    print(json.dumps({"status":status,"mean":round(mean,2),"std":round(std,2),"cv":round(cv,4),"n":n,"new_threshold":round(threshold,2)}))

if __name__ == "__main__":
    main()
