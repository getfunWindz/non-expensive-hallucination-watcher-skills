"""
adapt_threshold.py — Dual adaptation reading from turns.json.

Reads turns.json (instead of the old permanent.json), analyses trigger
patterns, and auto-tunes the detection threshold and redundancy scaling.

Also writes the decision result (triggered, formula_raw, zone, …) back
into the last turn entry in turns.json, and updates session.json
cumulative counters.

Co-requisite: session_store.py (sibling in scripts/)
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except json.JSONDecodeError:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


def save_params(proj, p):
    with open(
        Path(proj) / "hallucination-watch" / "params.json", "w", encoding="utf-8"
    ) as f:
        json.dump(p, f, indent=2, ensure_ascii=False)


def compute_ema(vals, a):
    if not vals:
        return None
    e = vals[0]
    for v in vals[1:]:
        e = a * e + (1 - a) * v
    return e


def main():
    d = json.loads(sys.stdin.read())
    proj, skill = d["project_dir"], d["skill_dir"]
    sid = d["session_id"]

    from session_store import (
        get_turns_by_phase,
        update_last_turn,
        read_session,
        write_session,
        ensure_session,
    )

    active = get_turns_by_phase(proj, sid, "active")
    if not active:
        print(json.dumps({"status": "skipped", "reason": "no active phase turns"}))
        return

    local_path = Path(proj) / "hallucination-watch" / "params.json"
    params = (
        load_json(local_path)
        if local_path.exists()
        else load_json(Path(skill) / "params" / "default.json")
    )

    old_th = params["threshold"]
    old_tpi = params.get("redundancy_tokens_per_increment", 1000000)
    old_inc = params.get("redundancy_increment", 10)

    total = len(active)
    triggered = sum(1 for r in active if r.get("triggered", False))
    rate = triggered / max(total, 1)
    target = params.get("target_trigger_rate", 0.10)
    margin = params.get("rate_margin", 0.02)
    inc_f = params.get("threshold_increase_factor", 1.10)
    dec_f = params.get("threshold_decrease_factor", 0.90)
    alpha = params.get("ema_alpha", 0.3)

    th = float(old_th)
    if rate > target + margin:
        th *= inc_f
    elif rate < target - margin:
        th *= dec_f
    raws = [r.get("formula_raw", 0) for r in active[-20:]]
    if raws:
        ema = compute_ema(raws, alpha)
        if ema and ema > 0 and th / ema > 100:
            th = ema * 50
    th = max(th, 1.0)

    recent = active[-min(len(active), 20):]
    rt = [r for r in recent if r.get("triggered")]
    cr = (
        sum(1 for r in rt if r.get("correction", {}).get("correction_applied"))
        / max(len(rt), 1)
        if rt
        else 0.0
    )

    tpi = float(old_tpi)
    inc = float(old_inc)
    mtpi = params.get("redundancy_min_tpi", 100000)
    xtpi = params.get("redundancy_max_tpi", 10000000)
    xinc = params.get("redundancy_max_increment", 50)
    if cr > 0.3:
        tpi = max(tpi * 0.9, mtpi)
    elif cr < 0.05:
        tpi = min(tpi * 1.1, xtpi)
    ct = [r.get("formula_raw", 0) for r in active[-10:]]
    if len(ct) >= 2 and (ct[-1] - ct[0]) / max(len(ct), 1) > 1000000:
        inc = min(inc * 1.2, xinc)
    tpi = max(mtpi, min(tpi, xtpi))
    inc = max(1, min(inc, xinc))

    params["threshold"] = round(th, 2)
    params["redundancy_tokens_per_increment"] = round(tpi)
    params["redundancy_increment"] = round(inc)
    params["_adapted_at"] = datetime.now(timezone.utc).isoformat()
    params["_trigger_rate"] = round(rate, 4)
    params["_correction_rate"] = round(cr, 4)
    save_params(proj, params)

    # ── Write decision result back to last turn ────────────────────
    zone = "safe"
    risk_score = 0.0
    if active:
        last = active[-1]
        last_turn_updates = {"phase": "active"}
        if last.get("triggered"):
            zone = "verify"
            risk_score = last.get("formula_raw", 0) / max(th, 1)
            last_turn_updates["formula_zone"] = zone
            last_turn_updates["risk_score"] = round(risk_score, 4)
        elif last.get("formula_raw", 0) > th * 0.5:
            zone = "mark"
            last_turn_updates["formula_zone"] = zone
        update_last_turn(proj, sid, last_turn_updates)

    # ── Update session.json cumulative counters ────────────────────
    sess = read_session(proj, sid)
    sess = ensure_session(sess)
    sess["cumulative"]["trigger_count"] = triggered
    last_t = active[-1] if active else {}
    sess["cumulative"]["total_tokens"] = last_t.get("total_tokens", 0)
    write_session(proj, sid, sess)

    print(json.dumps({
        "status": "adapted",
        "threshold": round(th, 2),
        "trigger_rate": round(rate, 4),
        "correction_rate": round(cr, 4),
        "tpi": round(tpi),
        "increment": round(inc),
    }))


if __name__ == "__main__":
    main()
