#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
monitor.py — 幻觉监测主控 v2（项目级，升级版）。
用法：
  init:   python monitor.py init
  check:  python monitor.py check --file=response.json
  status: python monitor.py status
  reset:  python monitor.py reset
"""
import sys, json, os, hashlib
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(BASE)
SESSIONS = os.path.join(PROJ, "sessions")
PARAMS_PATH = os.path.join(PROJ, "params", "default.json")

sys.path.insert(0, BASE)
from signal_keyword import detect as kw_detect
from signal_consistency import check as cs_check
from signal_fuzzy import process as fz_process
from signal_material import check as mt_check, add_entry as mt_add
from signal_habit import calc_bins, update_profile, anomaly_score
from signal_redundancy import calc as rd_calc
from signal_adapt import adapt as adapt_threshold

# ── IO helpers ─────────────────────────────────────────
def load_json(path):
    if not os.path.exists(path): return {}
    with open(path, encoding="utf-8") as f: return json.load(f)

def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)  # atomic on same filesystem

def _proj_root():
    """与 MCP 脚本一致：HW_PROJECT_ROOT 环境变量优先，回退到 cwd。"""
    return os.environ.get("HW_PROJECT_ROOT") or os.getcwd()

def active_session():
    """Return current session ID from .hw_active marker (not from directory scan)."""
    hw_active = os.path.join(_proj_root(), ".hw_active")
    if os.path.exists(hw_active):
        sid = open(hw_active).read().strip()
        if os.path.exists(os.path.join(SESSIONS, sid)):
            return sid
    if not os.path.exists(SESSIONS): return None
    all_s = sorted(os.listdir(SESSIONS), reverse=True)
    return all_s[0] if all_s else None

def sid_path(sid):
    return os.path.join(SESSIONS, sid)

# ── Phase calibration ──────────────────────────────────
def calibrate_phase(turn_num, params):
    mn = params.get("min_baseline_n", 3)
    mx = params.get("max_baseline_n", 10)
    if turn_num <= mn:
        return "baseline"
    elif turn_num > mx:
        return "active"
    else:
        # Transition zone: use if more than half way through
        return "baseline" if turn_num <= (mn + mx) // 2 else "active"

# ── Commands ────────────────────────────────────────────
def cmd_init():
    """幂等初始化：若 .hw_active 指向有效 session 则复用。"""
    hw_active = os.path.join(_proj_root(), ".hw_active")
    if os.path.exists(hw_active):
        existing_sid = open(hw_active).read().strip()
        if os.path.exists(sid_path(existing_sid)):
            print(json.dumps({"status": "reused", "session_id": existing_sid}))
            return existing_sid
    sid = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    sd = sid_path(sid)
    os.makedirs(sd, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    save_json(os.path.join(sd, "session.json"), {
        "session_id": sid, "created_at": now,
        "phase": "baseline", "next_turn": 1,
        "habit_profile": {"total_samples": 0, "bin_probs": [0.2, 0.2, 0.2, 0.2, 0.2], "dominant_bin": None, "raw_bins": [0, 0, 0, 0, 0]},
        "cumulative": {"total_checks": 0, "alert_count": 0, "correction_count": 0}
    })
    save_json(os.path.join(sd, "turns.json"), {"turns": []})
    save_json(os.path.join(sd, "reference.json"), {"entries": [], "last_updated": None})
    # Write marker
    with open(hw_active, "w") as f:
        f.write(sid)
    print(json.dumps({"status": "ok", "session_id": sid}))
    return sid

def cmd_check(text, prev_text=""):
    sid = active_session()
    if not sid:
        print(json.dumps({"error": "no session. run init first"})); return
    sd = sid_path(sid)
    params = load_json(PARAMS_PATH)
    session = load_json(os.path.join(sd, "session.json"))
    turns = load_json(os.path.join(sd, "turns.json"))
    reference = load_json(os.path.join(sd, "reference.json"))
    # per-session 有效阈值（EMA 自适应结果）优先，全局 params 兜底
    threshold = session.get("effective_threshold") or params.get("threshold", 20)
    tn = session.get("next_turn", 1)
    # redundancy 基于累计长度（完整长度，不受截断存储影响）
    total_text_len = session.get("cumulative_text_len", 0)

    # ── Run all signals ──────────────────────────────
    # 1. Keyword density
    kw_r = kw_detect(text, params)
    kw_score = kw_r.get("density", 0) * params.get("density_multiplier", 10)

    # 2. Consistency (Jaccard)
    cs_r = cs_check(text, prev_text)
    cs_score = cs_r.get("score", 0)

    # 3. Fuzzy match (hash-based fingerprint)
    fz_r = fz_process(text, prev_text, params.get("k_chars", 7))
    fz_score = fz_r.get("score", 0)

    # 4. Reference material (cross-turn fact consistency)
    mt_r = mt_check(text, reference.get("entries", []), params.get("topic_similarity_threshold", 0.15))
    mt_score = mt_r.get("score", 0)

    # 5. Redundancy
    rd_score = rd_calc(total_text_len, params)

    # 6. Habit profile
    bins = calc_bins(text, params.get("num_bins", 5))
    profile = update_profile(session.get("habit_profile", {}), bins)
    ha_score = anomaly_score(profile)

    # ── Decision formula ─────────────────────────────
    risk_raw = kw_score + cs_score + fz_score + mt_score + rd_score + ha_score
    risk_pct = (risk_raw / threshold) * 100 if threshold > 0 else 0

    zone = "safe"; triggered = False
    if risk_pct >= 100 and risk_pct < 250:
        zone = "mark"; triggered = True
    elif risk_pct >= 250:
        zone = "verify"; triggered = True

    # ── Phase calibration ────────────────────────────
    phase = calibrate_phase(tn, params)

    # ── Persist ─────────────────────────────────────
    # 存储截断 + 指纹（与 MCP 脚本一致）
    MAX_TEXT_STORED = 500
    stored_text = text
    if len(stored_text) > MAX_TEXT_STORED:
        stored_text = stored_text[:MAX_TEXT_STORED] + f"…[截断，原长{len(text)}]"
    text_fp = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]

    rec = {
        "turn": tn, "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": phase,
        "text": stored_text, "text_fp": text_fp,
        "keyword_density": kw_r.get("density", 0),
        "keyword_matches": [m["keyword"] for m in kw_r.get("matched", [])],
        "red_flags": [r["keyword"] for r in kw_r.get("red_flags", [])],
        "consistency_score": cs_score,
        "consistency_detail": cs_r.get("detail", ""),
        "fuzzy_similarity": fz_r.get("similarity", 0),
        "fuzzy_score": fz_score,
        "material_score": mt_score,
        "material_detail": mt_r.get("detail", ""),
        "redundancy_score": rd_score,
        "habit_anomaly": ha_score,
        "risk_raw": round(risk_raw, 3),
        "risk_pct": round(risk_pct, 1),
        "zone": zone,
        "triggered": triggered,
        "correction": None
    }
    if triggered and params.get("correction_enabled", False):
        from signal_correction import prioritize as correct
        kw_list = params.get("keywords", []) + params.get("red_flag_keywords", [])
        prior = correct(text, kw_list, params.get("max_claims_per_trigger", 3))
        rec["correction"] = {"claims": prior, "count": len(prior)}
    turns["turns"].append(rec)

    # Update session
    session["next_turn"] = tn + 1
    session["phase"] = phase
    session["habit_profile"] = profile
    session["cumulative"]["total_checks"] += 1
    session["cumulative_text_len"] = total_text_len + len(text)  # 完整长度累计
    if triggered:
        session["cumulative"]["alert_count"] += 1

    # Add to reference material if we have claims
    reference["entries"] = mt_add(reference.get("entries", []), text)
    reference["last_updated"] = datetime.now(timezone.utc).isoformat()

    save_json(os.path.join(sd, "turns.json"), turns)
    save_json(os.path.join(sd, "session.json"), session)
    save_json(os.path.join(sd, "reference.json"), reference)

    # ── EMA threshold adaptation（per-session：写入 session.json，不污染全局 params）──
    adapt_params = dict(params)
    adapt_params["threshold"] = threshold  # 从会话当前阈值起算（C1）
    adapt_result = adapt_threshold(turns.get("turns", []), adapt_params)
    if adapt_result:
        session["effective_threshold"] = adapt_result.get("threshold")
        session["threshold_adapted_at"] = adapt_result.get("_adapted_at")
        session["threshold_trigger_rate"] = adapt_result.get("_trigger_rate")
        save_json(os.path.join(sd, "session.json"), session)

    # ── Output report ───────────────────────────────
    report = {
        "zone": zone, "phase": phase, "turn": tn,
        "risk_pct": round(risk_pct, 1), "triggered": triggered,
        "signals": {
            "keyword": {
                "score": round(kw_score, 2),
                "density": round(kw_r.get("density", 0), 4),
                "matches": len(kw_r.get("matched", [])),
                "red_flags": len(kw_r.get("red_flags", []))
            },
            "consistency": {"score": round(cs_score, 2), "detail": cs_r.get("detail", "")},
            "fuzzy": {"similarity": fz_r.get("similarity", 0), "score": round(fz_score, 2)},
            "material": {"score": round(mt_score, 2), "detail": mt_r.get("detail", "")},
            "redundancy": {"score": round(rd_score, 2)},
            "habit": {"anomaly": round(ha_score, 3)}
        }
    }
    # Only show shelter card when triggered
    if triggered:
        report["card"] = {
            "status": "MARK" if zone == "mark" else "VERIFY",
            "risk_pct": round(risk_pct, 1),
            "top_signals": sorted(
                [k for k, v in report["signals"].items() if v.get("score", 0) > 0 or v.get("anomaly", 0) > 0],
                key=lambda k: report["signals"][k].get("score", report["signals"][k].get("anomaly", 0)),
                reverse=True
            )[:3]
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))

def cmd_status():
    sid = active_session()
    if not sid:
        print(json.dumps({"status": "no active session"})); return
    session = load_json(os.path.join(SESSIONS, sid, "session.json"))
    turns = load_json(os.path.join(SESSIONS, sid, "turns.json"))
    refs = load_json(os.path.join(SESSIONS, sid, "reference.json"))
    cum = session.get("cumulative", {})  # 旧格式 session 防御（与 MCP 一致）
    last5 = [{"turn": t["turn"], "zone": t["zone"],
              "risk_pct": t["risk_pct"],
              "sig": {k: round(v, 2) if isinstance(v, float) else v
                      for k, v in {"kw": t.get("keyword_density",0), "cs": t.get("consistency_score",0),
                                   "fz": t.get("fuzzy_score",0), "mt": t.get("material_score",0),
                                   "rd": t.get("redundancy_score",0), "ha": t.get("habit_anomaly",0)}.items()
                      if v and (isinstance(v, float) and v > 0) or (isinstance(v, str) and v)}}
             for t in turns.get("turns", [])[-5:]]
    print(json.dumps({
        "session_id": sid,
        "phase": session.get("phase"),
        "turn": session.get("next_turn"),
        "checks": cum.get("total_checks", 0),
        "alerts": cum.get("alert_count", 0),
        "reference_entries": len(refs.get("entries", [])),
        "habit_profile": session.get("habit_profile"),
        "last_turns": last5
    }, indent=2, ensure_ascii=False))

_HW_RULE_START = "<!-- hw-monitor:start -->"
_HW_RULE_END = "<!-- hw-monitor:end -->"

def _remove_agents_rule():
    """从项目根 AGENTS.md 移除监测规则块（与 MCP 脚本一致）。"""
    ap = os.path.join(_proj_root(), "AGENTS.md")
    if not os.path.exists(ap):
        return
    with open(ap, encoding="utf-8") as f:
        content = f.read()
    start = content.find(_HW_RULE_START)
    end = content.find(_HW_RULE_END)
    if start >= 0 and end >= 0:
        content = content[:start] + content[end + len(_HW_RULE_END):]
        content = content.strip() + "\n"
        with open(ap, "w", encoding="utf-8") as f:
            f.write(content)

def cmd_reset():
    sid = active_session()
    _remove_agents_rule()
    hw_active = os.path.join(_proj_root(), ".hw_active")
    if sid:
        import shutil; shutil.rmtree(sid_path(sid))
    if os.path.exists(hw_active):
        os.remove(hw_active)
    if sid:
        print(json.dumps({"status": "reset", "removed": sid, "note": "AGENTS.md 规则已移除"}))
    else:
        print(json.dumps({"status": "reset", "note": "AGENTS.md 规则已移除"}))

# ── CLI ────────────────────────────────────────────────
if __name__ == "__main__":
    args = sys.argv[1:] if len(sys.argv) > 1 else ["status"]
    if args[0] == "init":
        cmd_init()
    elif args[0] == "check":
        inp = ""
        if len(args) > 1 and args[1].startswith("--file="):
            fp = args[1].split("=", 1)[1]
            with open(fp, encoding="utf-8") as f: inp = f.read().strip()
        else:
            try: inp = sys.stdin.buffer.read().decode("utf-8").strip()
            except: inp = ""
        if not inp:
            print(json.dumps({"error": "use --file=path.json"}))
            sys.exit(1)
        d = json.loads(inp)
        cmd_check(d.get("text", ""), d.get("prev_text", ""))
    elif args[0] == "status":
        cmd_status()
    elif args[0] == "reset":
        cmd_reset()
    else:
        print("Usage: python monitor.py init|check|status|reset")
