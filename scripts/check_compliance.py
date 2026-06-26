#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Compliance verification script."""
import sys, json, os
from datetime import datetime, timezone

def check(project_root):
    hw_active = os.path.join(project_root, ".hw_active")
    if not os.path.exists(hw_active):
        return {"compliant": True, "reason": "not_active"}
    sid = open(hw_active).read().strip()
    sessions_dir = os.path.join(project_root, "hallucination-watch", "sessions")
    if not os.path.exists(os.path.join(sessions_dir, sid)):
        all_s = sorted(os.listdir(sessions_dir), reverse=True) if os.path.exists(sessions_dir) else []
        if not all_s: return {"compliant": False, "reason": "no_sessions"}
        sid = all_s[0]
    turns_path = os.path.join(sessions_dir, sid, "turns.json")
    if not os.path.exists(turns_path):
        return {"compliant": False, "reason": "no_turns_file"}
    with open(turns_path, encoding="utf-8") as f:
        turns = json.load(f).get("turns", [])
    if not turns:
        return {"compliant": False, "reason": "no_checks_yet", "turn_count": 0}
    latest = turns[-1]
    ts_str = latest.get("timestamp", "")
    if not ts_str: return {"compliant": False, "reason": "no_timestamp"}
    try:
        last_time = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        delta = (datetime.now(timezone.utc) - last_time).total_seconds()
    except:
        return {"compliant": False, "reason": "bad_timestamp"}
    if delta < 30:
        return {"compliant": True, "reason": "recently_checked", "last_turn": latest.get("turn"), "seconds_ago": round(delta, 1), "zone": latest.get("zone"), "risk_pct": latest.get("risk_pct")}
    else:
        return {"compliant": False, "reason": "stale_check", "last_turn": latest.get("turn"), "seconds_ago": round(delta, 1)}
