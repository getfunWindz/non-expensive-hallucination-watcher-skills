import json, sys
from datetime import datetime, timezone
from pathlib import Path

def load_json(p):
    try: return json.load(open(p, encoding="utf-8-sig"))
    except: return json.load(open(p, encoding="utf-8"))

def main():
    d = json.loads(sys.stdin.read())
    pp = Path(d["project_dir"]) / "hallucination-watch" / "sessions" / d["session_id"] / "permanent.json"
    if not pp.exists(): print(json.dumps({"status":"skipped"})); return
    perm = load_json(pp)
    active = [r for r in perm.get("results",[]) if r.get("phase")=="active"]
    if not active: print(json.dumps({"status":"skipped"})); return
    lp = Path(d["project_dir"]) / "hallucination-watch" / "params.json"
    params = load_json(lp) if lp.exists() else load_json(Path(d["skill_dir"]) / "params" / "default.json")
    th = float(params["threshold"])
    rate = sum(1 for r in active if r.get("triggered")) / max(len(active), 1)
    target = params.get("target_trigger_rate", 0.10)
    mar = params.get("rate_margin", 0.02)
    if rate > target+mar: th *= 1.10
    elif rate < target-mar: th *= 0.90
    raws = [r.get("formula_raw",0) for r in active[-20:]]
    if raws:
        e = raws[0]
        for v in raws[1:]: e = 0.3*e + 0.7*v
        if e > 0 and th / e > 100: th = e * 50
    params["threshold"] = round(max(th, 1.0), 2)
    params["_adapted_at"] = datetime.now(timezone.utc).isoformat()
    json.dump(params, open(lp, "w", encoding="utf-8"), indent=2)
    print(json.dumps({"status":"adapted","threshold":round(th,2),"trigger_rate":round(rate,4)}))

if __name__ == "__main__":
    main()
