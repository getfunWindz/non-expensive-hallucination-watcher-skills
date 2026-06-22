"""
reference_material.py — Reference material store, per-session isolation.

Path: {project}/hallucination-watch/sessions/{session_id}/reference.json
"""
import json, sys
from pathlib import Path
from datetime import datetime, timezone

SESSION_DIR = "hallucination-watch"
REF_FILENAME = "reference.json"  # was reference_material.json


def get_path(project_dir, session_id):
    return Path(project_dir) / SESSION_DIR / "sessions" / session_id / REF_FILENAME


def load(path):
    if path.exists():
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    return {"entries": [], "last_updated": None}


def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def topic_sim(sig_a, sig_b):
    if not sig_a or not sig_b:
        return 0.0
    return round(len(set(sig_a.keys()) & set(sig_b.keys())) / len(set(sig_a.keys()) | set(sig_b.keys())), 4)


def main():
    data = json.loads(sys.stdin.read())
    mode = data.get("mode", "add")
    proj = data["project_dir"]
    sid = data["session_id"]
    path = get_path(proj, sid)

    if mode == "add":
        mat = load(path)
        mat["entries"].append({
            "topic_sig": data.get("topic_sig", {}),
            "claims_text": (data.get("claims_text", "") or "")[:1000],
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        mat["last_updated"] = datetime.now(timezone.utc).isoformat()
        save(path, mat)
        print(json.dumps({"status": "added", "total_entries": len(mat["entries"])}))
    elif mode == "check":
        mat = load(path)
        if not mat["entries"]:
            print(json.dumps({"status": "no_material", "material_inconsistency": 0}))
            return
        cs = data.get("current_sig", {})
        if not cs:
            print(json.dumps({"status": "no_sig", "material_inconsistency": 0}))
            return
        matches = sum(1 for e in mat["entries"] if topic_sim(cs, e.get("topic_sig", {})) >= data.get("threshold", 0.15))
        penalty = max(0, 40 - matches * 8)
        print(json.dumps({"status": "checked", "topic_matches": matches, "material_inconsistency": penalty}))
    elif mode == "record":
        from session_store import update_last_turn
        update_last_turn(proj, sid,
                         {"material_inconsistency": data.get("material_inconsistency", 0)})
        print(json.dumps({"status": "recorded"}))


if __name__ == "__main__":
    main()
