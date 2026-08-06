#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
hallucination_watch_mcp.py — MCP Server for Hallucination Monitoring.

暴露4个工具：
  hw_init   → 初始化监测会话
  hw_check  → 对当前回复执行监测
  hw_status → 查看累计状态
  hw_reset  → 重置会话

stdio 传输，适用于本地 agent 集成。
"""
import os, sys, json, asyncio, hashlib
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

# turns.json 中单轮 text 的最大存储长度（超长截断，控制文件增长）。
# 截断只影响记录存储；redundancy 的长度统计走 session.cumulative_text_len（完整长度）。
MAX_TEXT_STORED = 500

# ── 路径 ──────────────────────────────────────────────
BASE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(BASE)        # 技能根目录（params/sessions 在此）
if os.environ.get("HW_PROJECT_ROOT"):
    PROJ_ROOT = os.environ["HW_PROJECT_ROOT"]
else:
    PROJ_ROOT = os.getcwd()              # opencode 启动 MCP 时 CWD=项目根
HW_ACTIVE = os.path.join(PROJ_ROOT, ".hw_active")
PARAMS_PATH = os.path.join(SKILL_DIR, "params", "default.json")
SESSIONS_DIR = os.path.join(SKILL_DIR, "sessions")
sys.path.insert(0, BASE)

# 延迟 import 信号模块（避免冷启动加载全部）
_signal_modules = {}

def _load_signals():
    """Lazy load signal modules on first tool call."""
    if _signal_modules:
        return
    from signal_keyword import detect as _kw
    from signal_consistency import check as _cs
    from signal_fuzzy import process as _fz
    from signal_material import check as _mt, add_entry as _add
    from signal_habit import calc_bins, update_profile, anomaly_score
    from signal_redundancy import calc as _rd
    from signal_adapt import adapt as _adapt
    from signal_correction import prioritize as _correct
    _signal_modules['kw'] = _kw
    _signal_modules['cs'] = _cs
    _signal_modules['fz'] = _fz
    _signal_modules['mt'] = _mt
    _signal_modules['add'] = _add
    _signal_modules['bins'] = calc_bins
    _signal_modules['profile'] = update_profile
    _signal_modules['anomaly'] = anomaly_score
    _signal_modules['rd'] = _rd
    _signal_modules['adapt'] = _adapt
    _signal_modules['correct'] = _correct

def _load_json(path):
    if not os.path.exists(path): return {}
    with open(path, encoding="utf-8") as f: return json.load(f)

def _save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def _active_session(sessions_dir):
    """返回当前会话 ID：优先 .hw_active 标记指向（与 hw_init 幂等逻辑一致），
    标记失效时回退到目录扫描最新。"""
    if os.path.exists(HW_ACTIVE):
        with open(HW_ACTIVE, encoding='utf-8') as f:
            sid = f.read().strip()
        if sid and os.path.isdir(os.path.join(sessions_dir, sid)):
            return sid
    if not os.path.exists(sessions_dir):
        return None
    all_s = sorted(os.listdir(sessions_dir), reverse=True)
    return all_s[0] if all_s else None

# ── MCP Server ───────────────────────────────────────
mcp = FastMCP("hallucination_watch_mcp")

# ── AGENTS.md 管理 ─────────────────────────────────
_HW_RULE_START = "<!-- hw-monitor:start -->"
_HW_RULE_END = "<!-- hw-monitor:end -->"
_HW_RULE_CONTENT = (
    "# Hallucination Monitoring Rules\n\n"
    "当项目根目录存在 `.hw_active` 文件时，以下规则强制生效：\n\n"
    "## 监测规则\n\n"
    "1. 每次生成完整回复后，必须调用 `hw_check` MCP 工具\n"
    "2. 调用方式：`hw_check(text=你的回复全文, prev_text=用户上一轮消息)`\n"
    "3. 调用后将返回的 zone 和 risk_pct 信息附加在回复末尾\n"
    "4. 如果 `triggered=true`，以卡片格式显示告警\n\n"
    "## 违反后果\n\n"
    "未调用 `hw_check` 的回复会被 `check_compliance.py` 检测到。\n"
    "连续3次违反将触发更严格的监督模式。\n"
)

def _agents_md_path():
    return os.path.join(PROJ_ROOT, "AGENTS.md")

def _ensure_agents_rule():
    """Append HW rules to AGENTS.md if not already present."""
    ap = _agents_md_path()
    existing = ""
    if os.path.exists(ap):
        with open(ap, encoding="utf-8") as f:
            existing = f.read()
    if _HW_RULE_START in existing:
        return  # already present
    with open(ap, "a", encoding="utf-8") as f:
        f.write("\n\n" + _HW_RULE_START + "\n" + _HW_RULE_CONTENT + _HW_RULE_END + "\n")

def _remove_agents_rule():
    """Remove HW rules from AGENTS.md."""
    ap = _agents_md_path()
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

@mcp.tool(
    name="hw_init",
    annotations={"title": "Init Monitoring Session", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False}
)
async def hw_init() -> str:
    """初始化（或复用）幻觉监测会话。

    幂等设计：若 .hw_active 存在且指向有效 session，直接复用。
    不再每次创建新 session，避免 opencode 重启后重复创建。
    同时在 AGENTS.md 中追加监测规则，确保每次提示词都包含规范。
    返回当前有效会话 ID。
    """
    sessions_dir = SESSIONS_DIR
    os.makedirs(sessions_dir, exist_ok=True)

    # 写入 AGENTS.md 规则
    _ensure_agents_rule()

    # 幂等：如果 .hw_active 指向一个有效 session，直接复用
    if os.path.exists(HW_ACTIVE):
        with open(HW_ACTIVE, encoding='utf-8') as f:
            existing_sid = f.read().strip()
        existing_sd = os.path.join(sessions_dir, existing_sid)
        if os.path.exists(existing_sd):
            return json.dumps({"status": "reused", "session_id": existing_sid, "note": "AGENTS.md 已追加监测规则"})

    # 否则创建新 session
    sid = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    sd = os.path.join(sessions_dir, sid)
    os.makedirs(sd, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    _save_json(os.path.join(sd, "session.json"), {
        "session_id": sid, "created_at": now,
        "phase": "baseline", "next_turn": 1,
        "habit_profile": {"total_samples": 0, "bin_probs": [0.2]*5, "dominant_bin": None, "raw_bins": [0]*5},
        "cumulative": {"total_checks": 0, "alert_count": 0, "correction_count": 0}
    })
    _save_json(os.path.join(sd, "turns.json"), {"turns": []})
    _save_json(os.path.join(sd, "reference.json"), {"entries": [], "last_updated": None})
    # Write marker
    with open(HW_ACTIVE, "w") as f:
        f.write(sid)
    return json.dumps({"status": "ok", "session_id": sid, "active_marker": HW_ACTIVE, "note": "AGENTS.md 已追加监测规则"})

@mcp.tool(
    name="hw_check",
    annotations={"title": "Run Hallucination Check", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False}
)
async def hw_check(text: str, prev_text: str = "") -> str:
    """对一段回复文本执行幻觉监测。

    执行6个信号分析（关键词密度、自洽性、模糊匹配、素材一致性、冗余度、习惯画像），
    返回三区域决策结果（safe/mark/verify）及详细信号分解。

    Args:
        text: 当前回复的完整文本
        prev_text: 上一轮对话文本（用于自洽性对比，可选）

    Returns:
        JSON 字符串，包含 zone/risk_pct/triggered/signals 字段
    """
    _load_signals()
    sessions_dir = SESSIONS_DIR
    os.makedirs(sessions_dir, exist_ok=True)

    sid = _active_session(sessions_dir)
    if not sid:
        return json.dumps({"error": "no session. call hw_init first"})
    sd = os.path.join(sessions_dir, sid)
    params = _load_json(PARAMS_PATH)
    session = _load_json(os.path.join(sd, "session.json"))
    turns = _load_json(os.path.join(sd, "turns.json"))
    reference = _load_json(os.path.join(sd, "reference.json"))
    # per-session 有效阈值（EMA 自适应结果）优先，全局 params 兜底
    threshold = session.get("effective_threshold") or params.get("threshold", 20)
    tn = session.get("next_turn", 1)
    # redundancy 基于累计长度（完整长度，不受截断存储影响）
    total_text_len = session.get("cumulative_text_len", 0)

    s = _signal_modules
    kw_r = s['kw'](text, params)
    cs_r = s['cs'](text, prev_text)
    fz_r = s['fz'](text, prev_text, params.get("k_chars", 7))
    mt_r = s['mt'](text, reference.get("entries", []), params.get("topic_similarity_threshold", 0.15))
    rd_score = s['rd'](total_text_len, params)
    bins = s['bins'](text, params.get("num_bins", 5))
    profile = s['profile'](session.get("habit_profile", {}), bins)
    ha_score = s['anomaly'](profile)

    kw_score = kw_r.get("density", 0) * params.get("density_multiplier", 10)
    risk_raw = kw_score + cs_r.get("score", 0) + fz_r.get("score", 0) + mt_r.get("score", 0) + rd_score + ha_score
    risk_pct = (risk_raw / threshold) * 100 if threshold > 0 else 0

    # Phase calibration
    mn = params.get("min_baseline_n", 3)
    mx = params.get("max_baseline_n", 10)
    phase = "baseline" if tn <= mn else ("active" if tn > mx else ("baseline" if tn <= (mn+mx)//2 else "active"))

    zone = "safe"; triggered = False
    red_flag_hard_trigger = False
    # 硬触发：红旗词 ≥2 直接 mark（不依赖密度归一化，防长文本稀释）
    red_count = len(kw_r.get("red_flags", []))
    if red_count >= 2:
        zone = "mark"; triggered = True
        red_flag_hard_trigger = True
        risk_pct = max(risk_pct, 100.0)  # 抬升至阈值线保持 zone/百分比自洽
    elif risk_pct >= 100 and risk_pct < 250:
        zone = "mark"; triggered = True
    elif risk_pct >= 250:
        zone = "verify"; triggered = True

    # Optional correction (default disabled)
    correction = None
    if triggered and params.get("correction_enabled", False):
        kw_list = params.get("keywords", []) + params.get("red_flag_keywords", [])
        prior = s['correct'](text, kw_list, params.get("max_claims_per_trigger", 3))
        correction = {"claims": prior, "count": len(prior)}

    # 存储截断 + 指纹（截断只影响记录，长度统计仍用完整 len(text)）
    stored_text = text
    if len(stored_text) > MAX_TEXT_STORED:
        stored_text = stored_text[:MAX_TEXT_STORED] + f"…[截断，原长{len(text)}]"
    text_fp = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]

    rec = {
        "turn": tn, "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": phase, "text": stored_text, "text_fp": text_fp,
        "keyword_density": kw_r.get("density", 0),
        "keyword_matches": [m["keyword"] for m in kw_r.get("matched", [])],
        "red_flags": [r["keyword"] for r in kw_r.get("red_flags", [])],
        "consistency_score": cs_r.get("score", 0),
        "consistency_detail": cs_r.get("detail", ""),
        "fuzzy_similarity": fz_r.get("similarity", 0),
        "fuzzy_score": fz_r.get("score", 0),
        "material_score": mt_r.get("score", 0),
        "material_detail": mt_r.get("detail", ""),
        "redundancy_score": rd_score,
        "habit_anomaly": ha_score,
        "risk_raw": round(risk_raw, 3), "risk_pct": round(risk_pct, 1),
        "zone": zone, "triggered": triggered, "red_flag_hard_trigger": red_flag_hard_trigger,
        "correction": correction
    }
    turns["turns"].append(rec)
    session["next_turn"] = tn + 1
    session["phase"] = phase
    session["habit_profile"] = profile
    session["cumulative"]["total_checks"] += 1
    session["cumulative_text_len"] = total_text_len + len(text)  # 完整长度累计
    if triggered:
        session["cumulative"]["alert_count"] += 1
    reference["entries"] = s['add'](reference.get("entries", []), text)
    reference["last_updated"] = datetime.now(timezone.utc).isoformat()

    _save_json(os.path.join(sd, "turns.json"), turns)
    _save_json(os.path.join(sd, "session.json"), session)
    _save_json(os.path.join(sd, "reference.json"), reference)

    # EMA threshold adaptation（per-session：基于会话有效阈值继续累计，不污染全局 params）
    adapt_params = dict(params)
    adapt_params["threshold"] = threshold  # 关键：从会话当前阈值起算，而非全局基准
    adapt_r = s['adapt'](turns.get("turns", []), adapt_params)
    if adapt_r:
        session["effective_threshold"] = adapt_r.get("threshold")
        session["threshold_adapted_at"] = adapt_r.get("_adapted_at")
        session["threshold_trigger_rate"] = adapt_r.get("_trigger_rate")
        _save_json(os.path.join(sd, "session.json"), session)

    report = {
        "zone": zone, "phase": phase, "turn": tn,
        "risk_pct": round(risk_pct, 1), "triggered": triggered,
        "red_flag_hard_trigger": red_flag_hard_trigger,
        "signals": {
            "keyword": {"score": round(kw_score, 2), "matches": len(kw_r.get("matched", [])), "red_flags": len(kw_r.get("red_flags", []))},
            "consistency": {"score": round(cs_r.get("score", 0), 2)},
            "fuzzy": {"similarity": fz_r.get("similarity", 0), "score": round(fz_r.get("score", 0), 2)},
            "material": {"score": round(mt_r.get("score", 0), 2)},
            "redundancy": {"score": round(rd_score, 2)},
            "habit": {"anomaly": round(ha_score, 3)}
        }
    }
    if triggered:
        top = sorted(report["signals"].items(), key=lambda x: x[1].get("score", x[1].get("anomaly", 0)), reverse=True)[:3]
        report["card"] = {"status": "MARK" if zone == "mark" else "VERIFY", "top_signals": [k for k, _ in top]}
    return json.dumps(report, ensure_ascii=False)

@mcp.tool(
    name="hw_status",
    annotations={"title": "Monitoring Session Status", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True}
)
async def hw_status() -> str:
    """查看当前监测会话的累计状态。

    返回会话轮次、检查次数、告警次数、参考素材条目数、
    习惯画像、最近3轮监测记录摘要。
    """
    sessions_dir = SESSIONS_DIR
    sid = _active_session(sessions_dir)
    if not sid:
        return json.dumps({"status": "no active session"})
    session = _load_json(os.path.join(sessions_dir, sid, "session.json"))
    turns = _load_json(os.path.join(sessions_dir, sid, "turns.json"))
    refs = _load_json(os.path.join(sessions_dir, sid, "reference.json"))
    cum = session.get("cumulative", {})  # 旧格式 session 防御
    last3 = [{"turn": t["turn"], "zone": t["zone"], "risk_pct": t["risk_pct"]}
             for t in turns.get("turns", [])[-3:]]
    return json.dumps({
        "session_id": sid, "phase": session.get("phase"),
        "turn": session.get("next_turn"),
        "checks": cum.get("total_checks", 0),
        "alerts": cum.get("alert_count", 0),
        "reference_entries": len(refs.get("entries", [])),
        "habit_profile": {k: v for k, v in session.get("habit_profile", {}).items() if k != "raw_bins"},
        "last_turns": last3
    }, ensure_ascii=False)

@mcp.tool(
    name="hw_reset",
    annotations={"title": "Reset Monitoring Session", "readOnlyHint": False, "destructiveHint": True, "idempotentHint": False}
)
async def hw_reset() -> str:
    """重置当前监测会话：删除 .hw_active 指向的会话、标记和 AGENTS.md 规则。
    孤儿会话（其他项目/历史残留）保留，避免跨项目误删。"""
    _remove_agents_rule()
    sessions_dir = SESSIONS_DIR
    removed = []
    sid = _active_session(sessions_dir)
    if sid:
        import shutil
        shutil.rmtree(os.path.join(sessions_dir, sid))
        removed.append(sid)
    if os.path.exists(HW_ACTIVE):
        os.remove(HW_ACTIVE)
    note = "AGENTS.md 规则已移除"
    if removed:
        note += f"；已删除会话 {removed[0]}"
    return json.dumps({"status": "reset", "removed": removed, "note": note})

if __name__ == "__main__":
    mcp.run()
