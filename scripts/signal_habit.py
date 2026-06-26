import sys, json

def calc_bins(text, num_bins=5):
    n = len(text)
    if n == 0: return [0] * num_bins
    bins = [0] * num_bins
    for i in range(n):
        bins[min(i * num_bins // n, num_bins - 1)] += 1
    return bins

def normalize(bins):
    total = sum(bins)
    if total == 0: return [1.0 / len(bins)] * len(bins)
    return [round(b / total, 4) for b in bins]

def update_profile(existing, new_bins):
    if not existing: existing = {"total_samples": 0, "bin_probs": [0.2]*5, "raw_bins": [0]*5}
    n = existing["total_samples"]
    new_probs = normalize(new_bins)
    old_raw = existing.get("raw_bins", [0]*5)
    merged = new_probs if n == 0 else [round((existing["bin_probs"][i] * n + new_probs[i]) / (n + 1), 4) for i in range(len(new_probs))]
    merged_raw = [old_raw[i] + new_bins[i] for i in range(len(old_raw))]
    dominant = merged.index(max(merged)) if max(merged) > 0.3 else None
    return {"total_samples": n + 1, "bin_probs": merged, "raw_bins": merged_raw, "dominant_bin": dominant}

def anomaly_score(profile):
    probs = profile.get("bin_probs", [0.2]*5)
    uniform = 1.0 / len(probs)
    return round(sum(abs(p - uniform) for p in probs), 3)
