#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
signal_habit.py — 习惯画像。
将文本字符位置分为 num_bins 个区间，统计模型输出字符在每区间的分布。
用于检测输出模式偏差（如过度集中在某类措辞区域）。
"""
import json, sys

def calc_bins(text, num_bins=5):
    """Compute character position distribution bins."""
    n = len(text)
    if n == 0:
        return [0] * num_bins
    bins = [0] * num_bins
    for i in range(n):
        bin_idx = min(i * num_bins // n, num_bins - 1)
        bins[bin_idx] += 1
    return bins

def normalize(bins):
    """Convert counts to probabilities."""
    total = sum(bins)
    if total == 0:
        return [1.0 / len(bins)] * len(bins)
    return [round(b / total, 4) for b in bins]

def update_profile(existing_profile, new_bins):
    """Update habit profile with new bin data (running average + raw sum)."""
    if not existing_profile:
        existing_profile = {"total_samples": 0, "bin_probs": [0.2]*5, "raw_bins": [0]*5}
    n = existing_profile["total_samples"]
    old_probs = existing_profile["bin_probs"]
    old_raw = existing_profile.get("raw_bins", [0]*5)
    new_probs = normalize(new_bins)
    if n == 0:
        merged = new_probs
    else:
        merged = [
            round((old_probs[i] * n + new_probs[i]) / (n + 1), 4)
            for i in range(len(old_probs))
        ]
    merged_raw = [old_raw[i] + new_bins[i] for i in range(len(old_raw))]
    dominant = merged.index(max(merged)) if max(merged) > 0.3 else None
    return {
        "total_samples": n + 1,
        "bin_probs": merged,
        "raw_bins": merged_raw,
        "dominant_bin": dominant
    }

def anomaly_score(profile):
    """Compute anomaly score from profile (0 = normal, higher = more anomalous)."""
    probs = profile.get("bin_probs", [0.2]*5)
    uniform = 1.0 / len(probs)
    deviation = sum(abs(p - uniform) for p in probs)
    return round(deviation, 3)

if __name__ == "__main__":
    stdin = sys.stdin.read().strip()
    if stdin:
        inp = json.loads(stdin)
        if inp.get("mode") == "calc":
            bins = calc_bins(inp.get("text", ""), inp.get("num_bins", 5))
            result = normalize(bins)
            print(json.dumps({"bins": result}))
        elif inp.get("mode") == "profile":
            bins = calc_bins(inp.get("text", ""), inp.get("num_bins", 5))
            updated = update_profile(inp.get("profile", {}), bins)
            updated["anomaly"] = anomaly_score(updated)
            print(json.dumps(updated))
