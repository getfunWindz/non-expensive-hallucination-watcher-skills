import json, sys
from pathlib import Path

DATA_DIR_NAME = "hallucination-watch"

def main():
    data = json.loads(sys.stdin.read())
    project_dir = data["project_dir"]
    data_dir = Path(project_dir) / DATA_DIR_NAME
    data_dir.mkdir(parents=True, exist_ok=True)
    session_path = data_dir / "session.json"
    perm_path = data_dir / "permanent.json"
    first_time = False
    if session_path.exists():
        with open(session_path, "r", encoding="utf-8-sig") as f:
            session = json.load(f)
        conv = session.get("conversation_number", 0) + 1
        phase = session.get("phase", "baseline")
    else:
        first_time = True
        conv = 1
        phase = "baseline"
        session = {"conversation_number": 0, "phase": "baseline", "previous": None, "current": None, "cumulative_total": 0, "habit_profile": {"total_samples": 0, "bin_probs": [0.2]*5}}
    session["conversation_number"] = conv
    with open(session_path, "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2)
    if not perm_path.exists():
        with open(perm_path, "w", encoding="utf-8") as f:
            json.dump({"last_updated": None, "results": []}, f)
    print(json.dumps({"status": "ok", "conversation_number": conv, "phase": phase, "data_dir": str(data_dir), "first_time": first_time}))

if __name__ == "__main__":
    main()
