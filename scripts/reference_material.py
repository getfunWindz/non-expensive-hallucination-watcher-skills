import json, sys
from pathlib import Path
from datetime import datetime, timezone

def main():
    d = json.loads(sys.stdin.read())
    path = Path(d["project_dir"]) / "hallucination-watch" / "sessions" / d["session_id"] / "reference_material.json"
    mat = json.load(open(path, encoding="utf-8-sig")) if path.exists() else {"entries": [], "last_updated": None}
    if d.get("mode") == "add":
        mat["entries"].append({"topic_sig": d.get("topic_sig",{}), "claims_text": (d.get("claims_text","") or "")[:1000], "timestamp": datetime.now(timezone.utc).isoformat()})
        json.dump(mat, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print(json.dumps({"status": "added", "total": len(mat["entries"])}))
    elif d.get("mode") == "check":
        if not mat["entries"] or not d.get("current_sig",{}):
            print(json.dumps({"status": "no_material", "material_inconsistency": 0})); return
        cs, th = set(d["current_sig"].keys()), d.get("threshold", 0.15)
        m = sum(1 for e in mat["entries"] if len(set(e.get("topic_sig",{}).keys()) & cs) / max(len(set(e.get("topic_sig",{}).keys()) | cs), 1) >= th)
        print(json.dumps({"status": "checked" if m > 0 else "no_match", "material_inconsistency": max(0, 40 - m * 8)}))

if __name__ == "__main__":
    main()
