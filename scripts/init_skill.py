"""
init_skill.py — Initialise a hallucination-watch session.

Creates the following files inside sessions/{session_id}/:
  session.json    — session-level metadata
  turns.json      — per-turn metric array (starts empty)
  reference.json  — reference-material store (starts empty)

On subsequent calls (same session_id) it increments
`conversation_number` and returns the updated count.
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = "hallucination-watch"


def _is_pair(t: str) -> bool:
    """Return True for Chinese-style paired brackets, quotes, etc."""
    return t in {"（）", "()", "「」", "『』", "【】", "《》", "\"\"", "''"}


def main():
    data = json.loads(sys.stdin.read())
    project_dir = data["project_dir"]
    session_id = data.get("session_id",
                          datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))

    session_dir = Path(project_dir) / BASE_DIR / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    session_path = session_dir / "session.json"
    turns_path = session_dir / "turns.json"
    ref_path = session_dir / "reference.json"

    is_first_time = False
    conversation_number = 0

    if session_path.exists():
        with open(session_path, "r", encoding="utf-8-sig") as f:
            session = json.load(f)
        conversation_number = session.get("conversation_number", 0) + 1
        phase = session.get("phase", "baseline")
    else:
        is_first_time = True
        conversation_number = 1
        phase = "baseline"
        session = {
            "session_id": session_id,
            "project_dir": project_dir,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "phase": phase,
            "conversation_number": conversation_number,
            "habit_profile": {
                "total_samples": 0,
                "bin_probs": [0.2, 0.2, 0.2, 0.2, 0.2],
                "dominant_bin": None,
            },
            "cumulative": {
                "total_tokens": 0,
                "alert_count": 0,
                "correction_count": 0,
                "trigger_count": 0,
            },
        }

    session["conversation_number"] = conversation_number
    with open(session_path, "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2, ensure_ascii=False)

    if not turns_path.exists():
        with open(turns_path, "w", encoding="utf-8") as f:
            json.dump({"turns": []}, f, indent=2, ensure_ascii=False)

    if not ref_path.exists():
        with open(ref_path, "w", encoding="utf-8") as f:
            json.dump({"entries": [], "last_updated": None}, f,
                      indent=2, ensure_ascii=False)

    print(json.dumps({
        "status": "ok",
        "session_id": session_id,
        "conversation_number": conversation_number,
        "phase": phase,
        "session_dir": str(session_dir),
        "is_first_time": is_first_time,
    }))


if __name__ == "__main__":
    main()
