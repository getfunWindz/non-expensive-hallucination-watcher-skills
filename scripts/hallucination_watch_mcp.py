#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MCP Server for Hallucination Monitoring."""
import os, sys, json
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL_DIR = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _THIS_DIR); sys.path.insert(0, _SKILL_DIR)

import asyncio; from datetime import datetime, timezone
from mcp.server.fastmcp import FastMCP

PROJ_ROOT = os.environ.get("HW_PROJECT_ROOT", os.getcwd())
HW_ACTIVE = os.path.join(PROJ_ROOT, ".hw_active")
PARAMS_PATH = os.path.join(_SKILL_DIR, "params", "default.json")
SESSIONS_DIR = os.path.join(_SKILL_DIR, "sessions")
_signal = {}

def _load_s():
    if _signal: return
    from signal_keyword import detect as a; from signal_consistency import check as b
    from signal_fuzzy import process as c; from signal_material import check as d, add_entry as e
    from signal_habit import calc_bins as f, update_profile as g, anomaly_score as h
    from signal_redundancy import calc as i; from signal_adapt import adapt as j
    from signal_correction import prioritize as k
    for n, v in zip("abcdefghijk", [a,b,c,d,e,f,g,h,i,j,k]): _signal[n] = v

def _lj(p):
    if not os.path.exists(p): return {}
    with open(p, encoding="utf-8") as f: return json.load(f)

def _sj(p, d):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)

def _as():
    if not os.path.exists(SESSIONS_DIR): return None
    s = sorted(os.listdir(SESSIONS_DIR), reverse=True)
    return s[0] if s else None

_RS = "<!-- hw-monitor:start -->"; _RE = "<!-- hw-monitor:end -->"
_RC = "# Hallucination Monitoring Rules\n\n当项目根目录存在 `.hw_active` 文件时，以下规则强制生效：\n\n## 监测规则\n\n1. 每次生成完整回复后，必须调用 `hw_check` MCP 工具\n2. 调用方式：`hw_check(text=你的回复全文, prev_text=用户上一轮消息)`\n3. 调用后将返回的 zone 和 risk_pct 信息附加在回复末尾\n4. 如果 `triggered=true`，以卡片格式显示告警\n"

def _ensure():
    ap = os.path.join(PROJ_ROOT, "AGENTS.md")
    e = ""
    if os.path.exists(ap):
        with open(ap, encoding="utf-8") as f: e = f.read()
    if _RS in e: return
    with open(ap, "a", encoding="utf-8") as f: f.write("\n\n" + _RS + "\n" + _RC + _RE + "\n")

def _remove():
    ap = os.path.join(PROJ_ROOT, "AGENTS.md")
    if not os.path.exists(ap): return
    with open(ap, encoding="utf-8") as f: c = f.read()
    s = c.find(_RS); e = c.find(_RE)
    if s >= 0 and e >= 0:
        c = (c[:s] + c[e + len(_RE):]).strip() + "\n"
        with open(ap, "w", encoding="utf-8") as f: f.write(c)

mcp = FastMCP("hallucination_watch_mcp")

@mcp.tool(name="hw_init", annotations={"title": "Init Monitoring Session", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False})
async def hw_init():
    os.makedirs(SESSIONS_DIR, exist_ok=True); _ensure()
    if os.path.exists(HW_ACTIVE):
        sid = open(HW_ACTIVE).read().strip()
        if os.path.exists(os.path.join(SESSIONS_DIR, sid)):
            return json.dumps({"status": "reused", "session_id": sid})
    sid = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    sd = os.path.join(SESSIONS_DIR, sid); os.makedirs(sd, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    _sj(os.path.join(sd, "session.json"), {"session_id": sid, "created_at": now, "phase": "baseline", "next_turn": 1, "habit_profile": {"total_samples": 0, "bin_probs": [0.2]*5, "dominant_bin": None, "raw_bins": [0]*5}, "cumulative": {"total_checks": 0, "alert_count": 0, "correction_count": 0}})
    _sj(os.path.join(sd, "turns.json"), {"turns": []}); _sj(os.path.join(sd, "reference.json"), {"entries": [], "last_updated": None})
    with open(HW_ACTIVE, "w") as f: f.write(sid)
    return json.dumps({"status": "ok", "session_id": sid})

@mcp.tool(name="hw_check", annotations={"title": "Run Hallucination Check", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False})
async def hw_check(text: str, prev_text: str = ""):
    _load_s(); s = _signal; os.makedirs(SESSIONS_DIR, exist_ok=True)
    sid = _as()
    if not sid: return json.dumps({"error": "no session"})
    sd = os.path.join(SESSIONS_DIR, sid); params = _lj(PARAMS_PATH)
    session = _lj(os.path.join(sd, "session.json")); turns = _lj(os.path.join(sd, "turns.json"))
    reference = _lj(os.path.join(sd, "reference.json")); threshold = params.get("threshold", 20)
    tn = session.get("next_turn", 1); ttl = sum(len(t.get("text", "")) for t in turns.get("turns", []))
    kw_r = s["a"](text, params); cs_r = s["b"](text, prev_text)
    fz_r = s["c"](text, prev_text, params.get("k_chars", 7))
    mt_r = s["d"](text, reference.get("entries", [])); rd_s = s["i"](ttl, params)
    bins = s["f"](text, params.get("num_bins", 5)); pf = s["g"](session.get("habit_profile", {}), bins); ha_s = s["h"](pf)
    kw_s = kw_r.get("density", 0) * params.get("density_multiplier", 10)
    rr = kw_s + cs_r.get("score", 0) + fz_r.get("score", 0) + mt_r.get("score", 0) + rd_s + ha_s
    rp = (rr / threshold) * 100 if threshold > 0 else 0
    mn = params.get("min_baseline_n", 3); mx = params.get("max_baseline_n", 10)
    phase = "baseline" if tn <= mn else ("active" if tn > mx else ("baseline" if tn <= (mn+mx)//2 else "active"))
    zone = "safe"; trig = False
    if rp >= 100 and rp < 250: zone = "mark"; trig = True
    elif rp >= 250: zone = "verify"; trig = True
    corr = None
    if trig and params.get("correction_enabled", False):
        kl = params.get("keywords", []) + params.get("red_flag_keywords", [])
        prior = s["k"](text, kl, params.get("max_claims_per_trigger", 3))
        corr = {"claims": prior, "count": len(prior)}
    rec = {"turn": tn, "timestamp": datetime.now(timezone.utc).isoformat(), "phase": phase, "text": text, "keyword_density": kw_r.get("density", 0), "keyword_matches": [m["keyword"] for m in kw_r.get("matched", [])], "red_flags": [r["keyword"] for r in kw_r.get("red_flags", [])], "consistency_score": cs_r.get("score", 0), "consistency_detail": cs_r.get("detail", ""), "fuzzy_similarity": fz_r.get("similarity", 0), "fuzzy_score": fz_r.get("score", 0), "material_score": mt_r.get("score", 0), "material_detail": mt_r.get("detail", ""), "redundancy_score": rd_s, "habit_anomaly": ha_s, "risk_raw": round(rr, 3), "risk_pct": round(rp, 1), "zone": zone, "triggered": trig, "correction": corr}
    turns["turns"].append(rec); session["next_turn"] = tn + 1; session["phase"] = phase; session["habit_profile"] = pf
    session["cumulative"]["total_checks"] += 1
    if trig: session["cumulative"]["alert_count"] += 1
    reference["entries"] = s["e"](reference.get("entries", []), text)
    reference["last_updated"] = datetime.now(timezone.utc).isoformat()
    _sj(os.path.join(sd, "turns.json"), turns); _sj(os.path.join(sd, "session.json"), session)
    _sj(os.path.join(sd, "reference.json"), reference)
    ar = s["j"](turns.get("turns", []), params)
    if ar: params.update(ar); _sj(PARAMS_PATH, params)
    report = {"zone": zone, "phase": phase, "turn": tn, "risk_pct": round(rp, 1), "triggered": trig, "signals": {"keyword": {"score": round(kw_s, 2), "matches": len(kw_r.get("matched", [])), "red_flags": len(kw_r.get("red_flags", []))}, "consistency": {"score": round(cs_r.get("score", 0), 2)}, "fuzzy": {"similarity": fz_r.get("similarity", 0), "score": round(fz_r.get("score", 0), 2)}, "material": {"score": round(mt_r.get("score", 0), 2)}, "redundancy": {"score": round(rd_s, 2)}, "habit": {"anomaly": round(ha_s, 3)}}}
    if trig:
        top = sorted(report["signals"].items(), key=lambda x: x[1].get("score", x[1].get("anomaly", 0)), reverse=True)[:3]
        report["card"] = {"status": "MARK" if zone == "mark" else "VERIFY", "top_signals": [k for k, _ in top]}
    if corr: report["correction"] = corr
    return json.dumps(report, ensure_ascii=False)

@mcp.tool(name="hw_status", annotations={"title": "Monitoring Session Status", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def hw_status():
    sid = _as()
    if not sid: return json.dumps({"status": "no active session"})
    session = _lj(os.path.join(SESSIONS_DIR, sid, "session.json"))
    turns = _lj(os.path.join(SESSIONS_DIR, sid, "turns.json"))
    refs = _lj(os.path.join(SESSIONS_DIR, sid, "reference.json"))
    l3 = [{"turn": t["turn"], "zone": t["zone"], "risk_pct": t["risk_pct"]} for t in turns.get("turns", [])[-3:]]
    return json.dumps({"session_id": sid, "phase": session.get("phase"), "turn": session.get("next_turn"), "checks": session["cumulative"]["total_checks"], "alerts": session["cumulative"]["alert_count"], "reference_entries": len(refs.get("entries", [])), "last_turns": l3}, ensure_ascii=False)

@mcp.tool(name="hw_reset", annotations={"title": "Reset Monitoring Session", "readOnlyHint": False, "destructiveHint": True, "idempotentHint": False})
async def hw_reset():
    _remove(); sid = _as()
    if not sid: return json.dumps({"status": "reset"})
    import shutil; shutil.rmtree(os.path.join(SESSIONS_DIR, sid))
    if os.path.exists(HW_ACTIVE): os.remove(HW_ACTIVE)
    return json.dumps({"status": "reset", "removed": sid})

if __name__ == "__main__": mcp.run()
