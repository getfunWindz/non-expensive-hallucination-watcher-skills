import sys, json

def compute_ema(values, alpha=0.3):
    if not values: return None
    e = values[0]
    for v in values[1:]: e = alpha * e + (1 - alpha) * v
    return e

def adapt(turns, params):
    interval = params.get("adaptation_interval", 10)
    if len(turns) < interval or len(turns) % interval != 0: return {}
    recent = turns[-interval:]
    total = len(recent)
    triggered = sum(1 for t in recent if t.get("triggered", False))
    rate = triggered / max(total, 1)
    target = params.get("target_trigger_rate", 0.10)
    margin = params.get("rate_margin", 0.02)
    th = float(params.get("threshold", 20))
    if rate > target + margin: th *= params.get("threshold_increase_factor", 1.10)
    elif rate < target - margin: th *= params.get("threshold_decrease_factor", 0.90)
    raws = [t.get("risk_raw", 0) for t in recent if t.get("risk_raw", 0) > 0]
    if raws:
        ema = compute_ema(raws, params.get("ema_alpha", 0.3))
        if ema and ema > 0 and th / ema > 50: th = ema * 25
    th = max(min(th, 500.0), 5.0)
    if abs(th - float(params.get("threshold", 20))) / max(float(params.get("threshold", 20)), 1) < 0.01: return {}
    import datetime
    return {"threshold": round(th, 2), "_adapted_at": datetime.datetime.utcnow().isoformat(), "_trigger_rate": round(rate, 4)}
