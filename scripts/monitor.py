#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CLI monitor entry point for hallucination-watch."""
import sys, json, os; from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
SESSIONS = os.path.join(SKILL_DIR, "sessions")
PARAMS_PATH = os.path.join(SKILL_DIR, "params", "default.json")
sys.path.insert(0, SCRIPT_DIR)

from signal_keyword import detect as kw_detect; from signal_consistency import check as cs_check
from signal_fuzzy import process as fz_process; from signal_material import check as mt_check, add_entry as mt_add
from signal_habit import calc_bins, update_profile, anomaly_score; from signal_redundancy import calc as rd_calc
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

def sid_path(sid): return os.path.join(SESSIONS, sid)

def calibrate_phase(tn, params):
    mn = params.get("min_baseline_n", 3); mx = params.get("max_baseline_n", 10)
    if tn <= mn: return "baseline"
    if tn > mx: return "active"
    return "baseline" if tn <= (mn + mx) // 2 else "active"

def cmd_init():
    hw_active = os.path.join(SKILL_DIR, "..", ".hw_active")
    if os.path.exists(hw_active):
        sid = open(hw_active).read().strip()
        if os.path.exists(sid_path(sid)):
            print(json.dumps({"status": "reused", "session_id": sid})); return sid
    sid = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    sd = sid_path(sid); os.makedirs(sd, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    save_json(os.path.join(sd, "session.json"), {"session_id": sid, "created_at": now, "phase": "baseline", "next_turn": 1, "habit_profile": {"total_samples": 0, "bin_probs": [0.2]*5, "dominant_bin": None, "raw_bins": [0]*5}, "cumulative": {"total_checks": 0, "alert_count": 0, "correction_count": 0}})
    save_json(os.path.join(sd, "turns.json"), {"turns": []})
    save_json(os.path.join(sd, "reference.json"), {"entries": [], "last_updated": None})
    with open(hw_active, "w") as f: f.write(sid)
    print(json.dumps({"status": "ok", "session_id": sid})); return sid

def cmd_check(text, prev_text=""):
    sid = active_session()
    if not sid: print(json.dumps({"error": "no session"})); return
    sd = sid_path(sid); params = load_json(PARAMS_PATH)
    session = load_json(os.path.join(sd, "session.json")); turns = load_json(os.path.join(sd, "turns.json"))
    reference = load_json(os.path.join(sd, "reference.json")); threshold = params.get("threshold", 20)
    tn = session.get("next_turn", 1); total_text_len = sum(len(t.get("text", "")) for t in turns.get("turns", []))
    kw_r = kw_detect(text, params); cs_r = cs_check(text, prev_text)
    fz_r = fz_process(text, prev_text, params.get("k_chars", 7))
    mt_r = mt_check(text, reference.get("entries", []))
    rd_score = rd_calc(total_text_len, params)
    bins = calc_bins(text, params.get("num_bins", 5))
    profile = update_profile(session.get("habit_profile", {}), bins); ha_score = anomaly_score(profile)
    kw_score = kw_r.get("density", 0) * params.get("density_multiplier", 10)
    risk_raw = kw_score + cs_r.get("score", 0) + fz_r.get("score", 0) + mt_r.get("score", 0) + rd_score + ha_score
    risk_pct = (risk_raw / threshold) * 100 if threshold > 0 else 0
    phase = calibrate_phase(tn, params)
    zone = "safe"; triggered = False
    if risk_pct >= 100 and risk_pct < 250: zone = "mark"; triggered = True
    elif risk_pct >= 250: zone = "verify"; triggered = True
    rec = {"turn": tn, "timestamp": datetime.now(timezone.utc).isoformat(), "phase": phase, "text": text, "keyword_density": kw_r.get("density", 0), "keyword_matches": [m["keyword"] for m in kw_r.get("matched", [])], "red_flags": [r["keyword"] for r in kw_r.get("red_flags", [])], "consistency_score": cs_r.get("score", 0), "consistency_detail": cs_r.get("detail", ""), "fuzzy_similarity": fz_r.get("similarity", 0), "fuzzy_score": fz_r.get("score", 0), "material_score": mt_r.get("score", 0), "material_detail": mt_r.get("detail", ""), "redundancy_score": rd_score, "habit_anomaly": ha_score, "risk_raw": round(risk_raw, 3), "risk_pct": round(risk_pct, 1), "zone": zone, "triggered": triggered, "correction": None}
    turns["turns"].append(rec)
    session["next_turn"] = tn + 1; session["phase"] = phase; session["habit_profile"] = profile
    session["cumulative"]["total_checks"] += 1
    if triggered: session["cumulative"]["alert_count"] += 1
    reference["entries"] = mt_add(reference.get("entries", []), text)
    reference["last_updated"] = datetime.now(timezone.utc).isoformat()
    save_json(os.path.join(sd, "turns.json"), turns)
    save_json(os.path.join(sd, "session.json"), session)
    save_json(os.path.join(sd, "reference.json"), reference)
    adapt_result = adapt_threshold(turns.get("turns", []), params)
    if adapt_result: params.update(adapt_result); save_json(PARAMS_PATH, params)
    report = {"zone": zone, "phase": phase, "turn": tn, "risk_pct": round(risk_pct, 1), "triggered": triggered, "signals": {"keyword": {"score": round(kw_score, 2), "matches": len(kw_r.get("matched", [])), "red_flags": len(kw_r.get("red_flags", []))}, "consistency": {"score": round(cs_r.get("score", 0), 2)}, "fuzzy": {"similarity": fz_r.get("similarity", 0), "score": round(fz_r.get("score", 0), 2)}, "material": {"score": round(mt_r.get("score", 0), 2)}, "redundancy": {"score": round(rd_score, 2)}, "habit": {"anomaly": round(ha_score, 3)}}}
    if triggered: top = sorted(report["signals"].items(), key=lambda x: x[1].get("score", x[1].get("anomaly", 0)), reverse=True)[:3]; report["card"] = {"status": "MARK" if zone == "mark" else "VERIFY", "top_signals": [k for k, _ in top]}
    print(json.dumps(report, ensure_ascii=False, indent=2))

def cmd_status():
    sid = active_session()
    if not sid: print(json.dumps({"status": "no active session"})); return
    session = load_json(os.path.join(SESSIONS, sid, "session.json"))
    turns = load_json(os.path.join(SESSIONS, sid, "turns.json"))
    refs = load_json(os.path.join(SESSIONS, sid, "reference.json"))
    last5 = [{"turn": t["turn"], "zone": t["zone"], "risk_pct": t["risk_pct"]} for t in turns.get("turns", [])[-5:]]
    print(json.dumps({"session_id": sid, "phase": session.get("phase"), "turn": session.get("next_turn"), "checks": session["cumulative"]["total_checks"], "alerts": session["cumulative"]["alert_count"], "reference_entries": len(refs.get("entries", [])), "last_turns": last5}, indent=2, ensure_ascii=False))

def cmd_reset():
    sid = active_session()
    if sid:
        import shutil; shutil.rmtree(sid_path(sid))
        hw_active = os.path.join(SKILL_DIR, "..", ".hw_active")
        if os.path.exists(hw_active): os.remove(hw_active)
        print(json.dumps({"status": "reset", "removed": sid}))
    else: print(json.dumps({"status": "nothing to reset"}))

if __name__ == "__main__":
    args = sys.argv[1:] if len(sys.argv) > 1 else ["status"]
    if args[0] == "init": cmd_init()
    elif args[0] == "check":
        inp = ""
        if len(args) > 1 and args[1].startswith("--file="):
            with open(args[1].split("=", 1)[1], encoding="utf-8") as f: inp = f.read().strip()
        else:
            try: inp = sys.stdin.buffer.read().decode("utf-8").strip()
            except: inp = ""
        if not inp: print(json.dumps({"error": "use --file=path.json"})); sys.exit(1)
        d = json.loads(inp); cmd_check(d.get("text", ""), d.get("prev_text", ""))
    elif args[0] == "status": cmd_status()
    elif args[0] == "reset": cmd_reset()
    else: print("Usage: python monitor.py init|check|status|reset")
