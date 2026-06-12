import json, sys
from pathlib import Path
from datetime import datetime

BASE_DIR = "hallucination-watch"

def main():
    d = json.loads(sys.stdin.read())
    sid = d.get("session_id", datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
    sdir = Path(d["project_dir"]) / BASE_DIR / "sessions" / sid
    sdir.mkdir(parents=True, exist_ok=True)
    sp = sdir / "session.json"
    pp = sdir / "permanent.json"
    first = False
    if sp.exists():
        s = json.load(open(sp, encoding="utf-8-sig"))
        cn = s.get("conversation_number", 0) + 1
        ph = s.get("phase", "baseline")
    else:
        first = True; cn = 1; ph = "baseline"
        s = {"conversation_number": 0, "phase": "baseline", "previous": None, "current": None, "cumulative_total": 0, "habit_profile": {"total_samples": 0, "bin_probs": [0.2]*5}}
    s["conversation_number"] = cn
    json.dump(s, open(sp, "w", encoding="utf-8"), indent=2)
    if not pp.exists():
        json.dump({"last_updated": None, "results": []}, open(pp, "w", encoding="utf-8"), indent=2)
    print(json.dumps({"status": "ok", "session_id": sid, "conversation_number": cn, "phase": ph, "session_dir": str(sdir)}))

if __name__ == "__main__":
    main()
