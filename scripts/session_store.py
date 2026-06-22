"""
session_store.py — Unified data access layer for hallucination-watch.

Provides atomic read/write/append access to turns.json, session.json, and
reference.json.  All paths are derived from project_dir + session_id,
ensuring per-session isolation.  Every write is a read-modify-write cycle
so concurrent callers are serialised by the shell pipeline.

CLI modes (stdin JSON, stdout JSON):
  update_last_turn   — Merge key-value pairs into the last turn entry
  append_new_turn    — Pre-allocate a new empty turn
  get_turns          — Return turn count (lightweight health check)
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

BASE = "hallucination-watch"


# ── paths ──────────────────────────────────────────────────────────

def _turns_path(proj, sid):
    return Path(proj) / BASE / "sessions" / sid / "turns.json"


def _session_path(proj, sid):
    return Path(proj) / BASE / "sessions" / sid / "session.json"


def _ref_path(proj, sid):
    return Path(proj) / BASE / "sessions" / sid / "reference.json"


# ── readers / writers ──────────────────────────────────────────────

def read_turns(proj, sid):
    p = _turns_path(proj, sid)
    return json.loads(p.read_text("utf-8-sig")) if p.exists() else {"turns": []}


def write_turns(proj, sid, data):
    p = _turns_path(proj, sid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")


def read_session(proj, sid):
    p = _session_path(proj, sid)
    return json.loads(p.read_text("utf-8-sig")) if p.exists() else {}


def write_session(proj, sid, data):
    p = _session_path(proj, sid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")


def read_ref(proj, sid):
    p = _ref_path(proj, sid)
    return json.loads(p.read_text("utf-8-sig")) if p.exists() else {"entries": [], "last_updated": None}


def write_ref(proj, sid, data):
    p = _ref_path(proj, sid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")


# ── turn helpers ───────────────────────────────────────────────────

def update_last_turn(proj, sid, updates):
    """Merge *updates* into the last turn entry.  Creates the first
    turn (turn=1) if the turns array is empty."""
    turns = read_turns(proj, sid)
    if not turns["turns"]:
        turns["turns"].append({
            "turn": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    for k, v in updates.items():
        turns["turns"][-1][k] = v
    write_turns(proj, sid, turns)


def append_new_turn(proj, sid, turn_number):
    """Pre-allocate an empty turn entry.  Returns the new length."""
    turns = read_turns(proj, sid)
    turns["turns"].append({
        "turn": turn_number,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    write_turns(proj, sid, turns)
    return len(turns["turns"])


def get_turns_by_phase(proj, sid, phase):
    """Return only turns whose ``phase`` field matches *phase*."""
    return [t for t in read_turns(proj, sid)["turns"] if t.get("phase") == phase]


def ensure_session(session):
    """Backfill any missing top-level / cumulative / habit_profile keys
    so downstream code never hits a KeyError on a legacy or partial
    object."""
    if "cumulative" not in session:
        session["cumulative"] = {
            "total_tokens": 0,
            "alert_count": 0,
            "correction_count": 0,
            "trigger_count": 0,
        }
    if "habit_profile" not in session:
        session["habit_profile"] = {
            "total_samples": 0,
            "bin_probs": [0.2] * 5,
            "dominant_bin": None,
        }
    return session


# ── CLI entry points ───────────────────────────────────────────────

def _cli_update_last_turn(data):
    proj = data["project_dir"]
    sid = data["session_id"]
    updates = {k: v for k, v in data.items()
               if k not in ("mode", "project_dir", "session_id")}
    if updates:
        update_last_turn(proj, sid, updates)
    print(json.dumps({"status": "updated", "fields": list(updates.keys())}))


def _cli_append_new_turn(data):
    proj = data["project_dir"]
    sid = data["session_id"]
    tn = data.get("turn", 1)
    append_new_turn(proj, sid, tn)
    print(json.dumps({"status": "appended", "turn": tn}))


def _cli_get_turns(data):
    proj = data["project_dir"]
    sid = data["session_id"]
    turns = read_turns(proj, sid)
    print(json.dumps({
        "status": "ok",
        "turn_count": len(turns["turns"]),
    }))


def main():
    data = json.loads(sys.stdin.read())
    mode = data.get("mode", "update_last_turn")

    if mode == "update_last_turn":
        _cli_update_last_turn(data)
    elif mode == "append_new_turn":
        _cli_append_new_turn(data)
    elif mode == "get_turns":
        _cli_get_turns(data)
    else:
        print(json.dumps({"error": f"unknown mode: {mode}"}))


if __name__ == "__main__":
    main()
