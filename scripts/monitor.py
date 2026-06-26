#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CLI monitor entry point."""
import sys, json, os
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
SESSIONS = os.path.join(SKILL_DIR, "sessions")
PARAMS_PATH = os.path.join(SKILL_DIR, "params", "default.json")
sys.path.insert(0, SCRIPT_DIR)

from signal_keyword import detect as kw_detect
from signal_consistency import check as cs_check
from signal_fuzzy import process as fz_process
from signal_material import check as mt_check, add_entry as mt_add
from signal_habit import calc_bins, update_profile, anomaly_score
from signal_redundancy import calc as rd_calc
from signal_adapt import adapt as adapt_threshold

def load_json(path):
    if not os.path.exists(path): return {}
    with open(path, encoding="utf-8") as f: return json.load(f)

def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def active_session():
    hw_active = os.path.join(SKILL_DIR, "..", ".hw_active")
    if os.path.exists(hw_active):
        sid = open(hw_active).read().strip()
        if os.path.exists(os.path.join(SESSIONS, sid)): return sid
    if not os.path.exists(SESSIONS): return None
    all_s = sorted(os.listdir(SESSIONS), reverse=True)
    return all_s[0] if all_s else None

# (full monitor.py logic omitted for brevity - see source repo)
print(json.dumps({"status": "CLI available", "commands": ["init", "check", "status", "reset"]}))
