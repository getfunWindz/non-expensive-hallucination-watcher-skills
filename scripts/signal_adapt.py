#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
signal_adapt.py — EMA 阈值自适应。

每 N 轮根据最近 trigger_rate 调整 threshold：
  - trigger_rate > target + margin → threshold *= increase_factor
  - trigger_rate < target - margin → threshold *= decrease_factor
  - 用 EMA 平滑 risk_raw，防止单次异常值导致阈值剧烈跳变
"""
import json

def compute_ema(values, alpha=0.3):
    """Exponential Moving Average."""
    if not values:
        return None
    e = values[0]
    for v in values[1:]:
        e = alpha * e + (1 - alpha) * v
    return e

def adapt(turns, params):
    """Analyze trigger patterns and return adjusted params dict.
    
    Args:
        turns: list of turn records from turns.json
        params: current params dict
    
    Returns:
        dict with updated params (or empty if no adaptation needed)
    """
    interval = params.get("adaptation_interval", 10)
    if len(turns) < interval:
        return {}  # not enough data
    
    # Only adapt on exact interval boundaries
    if len(turns) % interval != 0:
        return {}

    # Only consider active phase turns (skip baseline)
    active_turns = [t for t in turns if t.get("phase") in ("active", None)]
    if len(active_turns) < interval:
        # Use all available if not in active phase yet
        active_turns = turns
    if len(active_turns) < max(interval // 2, 3):
        return {}

    recent = active_turns[-interval:]
    total = len(recent)
    triggered = sum(1 for t in recent if t.get("triggered", False))
    rate = triggered / max(total, 1)

    target = params.get("target_trigger_rate", 0.10)
    margin = params.get("rate_margin", 0.02)
    inc_f = params.get("threshold_increase_factor", 1.10)
    dec_f = params.get("threshold_decrease_factor", 0.90)
    alpha = params.get("ema_alpha", 0.3)

    old_th = params.get("threshold", 20)
    th = float(old_th)

    # Adjust based on trigger rate
    if rate > target + margin:
        th *= inc_f
    elif rate < target - margin:
        th *= dec_f

    # EMA-based sanity check: prevent threshold from drifting too far
    raws = [t.get("risk_raw", 0) for t in recent if t.get("risk_raw", 0) > 0]
    if raws:
        ema = compute_ema(raws, alpha)
        if ema and ema > 0 and th / ema > 50:
            th = ema * 25  # pull threshold back toward recent risk levels

    th = max(th, 5.0)   # floor
    th = min(th, 500.0) # ceiling

    if abs(th - old_th) / max(old_th, 1) < 0.01:
        return {}  # change too small

    return {
        "threshold": round(th, 2),
        "_adapted_at": __import__("datetime").datetime.utcnow().isoformat(),
        "_trigger_rate": round(rate, 4)
    }
