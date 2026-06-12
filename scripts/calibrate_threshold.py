import json, sys
from pathlib import Path

def load_json(p):
    try: return json.load(open(p, encoding="utf-8-sig"))
    except: return json.load(open(p, encoding="utf-8"))

def main():
    d = json.loads(sys.stdin.read())
    pp = Path(d["project_dir"]) / "hallucination-watch" / "sessions" / d["session_id"] / "permanent.json"
    if not pp.exists(): print(json.dumps({"status":"skipped"})); return
    perm = load_json(pp)
    raws = [r["formula_raw"] for r in perm.get("results",[]) if r.get("phase")=="baseline" and "formula_raw" in r]
    if len(raws) < 6: print(json.dumps({"status":"skipped","n":len(raws)})); return
    m = sum(raws)/len(raws)
    s = (sum((r-m)**2 for r in raws)/len(raws))**0.5
    cv = s/m if m > 0 else 0.0
    status = "calibrated" if cv <= 0.3 else "extend"
    if status == "calibrated":
        th = max(m + 3.0 * s, 100)
        lp = Path(d["project_dir"]) / "hallucination-watch" / "params.json"
        p = load_json(lp) if lp.exists() else {}
        p["threshold"] = round(th, 2)
        p["_calibrated_at"] = True
        json.dump(p, open(lp, "w", encoding="utf-8"), indent=2)
        print(json.dumps({"status":"calibrated","mean":round(m,2),"std":round(s,2),"n":len(raws),"new_threshold":round(th,2)}))
    else:
        print(json.dumps({"status":"extend","cv":round(cv,4)}))

if __name__ == "__main__":
    main()
