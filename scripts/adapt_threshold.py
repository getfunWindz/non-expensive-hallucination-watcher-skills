import json, sys
from datetime import datetime, timezone
from pathlib import Path

def load_json(path):
    try:
        with open(path,"r",encoding="utf-8-sig") as f: return json.load(f)
    except json.JSONDecodeError:
        with open(path,"r",encoding="utf-8") as f: return json.load(f)

def compute_ema(values, alpha):
    if not values: return None
    ema = values[0]
    for v in values[1:]: ema = alpha*ema + (1-alpha)*v
    return ema

def main():
    data = json.loads(sys.stdin.read())
    project_dir, skill_dir = data["project_dir"], data["skill_dir"]
    perm_path = Path(project_dir) / "hallucination-watch" / "permanent.json"
    if not perm_path.exists():
        print(json.dumps({"status":"skipped","reason":"no permanent.json"}))
        return
    permanent = load_json(perm_path)
    active = [r for r in permanent.get("results",[]) if r.get("phase")=="active"]
    if not active:
        print(json.dumps({"status":"skipped","reason":"no active data"}))
        return
    params_path = Path(project_dir) / "hallucination-watch" / "params.json"
    if params_path.exists():
        params = load_json(params_path)
    else:
        print(json.dumps({"status":"skipped","reason":"no params.json"}))
        return
    total = len(active)
    triggered = sum(1 for r in active if r.get("triggered",False))
    rate = triggered/max(total,1)
    target = params.get("target_trigger_rate",0.10)
    margin = params.get("rate_margin",0.02)
    inc = params.get("threshold_increase_factor",1.10)
    dec = params.get("threshold_decrease_factor",0.90)
    alpha = params.get("ema_alpha",0.3)
    threshold = float(params["threshold"])
    old = threshold
    if rate > target + margin: threshold *= inc
    elif rate < target - margin: threshold *= dec
    raws = [r.get("formula_raw",0) for r in active[-20:]]
    if raws:
        ema = compute_ema(raws, alpha)
        if ema and ema>0 and threshold/ema>100:
            threshold = ema*50
    threshold = max(threshold, 1.0)
    params["threshold"] = round(threshold,2)
    params["_adapted_at"] = datetime.now(timezone.utc).isoformat()
    with open(params_path,"w",encoding="utf-8") as f:
        json.dump(params,f,indent=2,ensure_ascii=False)
    print(json.dumps({"status":"adapted","old_threshold":old,"new_threshold":round(threshold,2),"trigger_rate":round(rate,4)}))

if __name__ == "__main__":
    main()
