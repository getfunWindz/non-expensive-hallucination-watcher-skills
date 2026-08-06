#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
signal_correction.py — 自动纠错模块（默认关闭）。

功能（从原版 correction.py 精简）：
  1. 当 trigger=true 时，从当前 text 中提取高优先级声明
  2. 按 proximity to subjective keywords 给声明打分排序
  3. 返回待验证的声明列表（供外部校验）

默认不启用（correction_enabled: false）。
"""
import re

def extract_claims(text):
    """Extract assertion sentences from text."""
    sents = re.split(r'[。！？\n]', text)
    return [s.strip() for s in sents if len(s.strip()) >= 8]

def find_keyword_positions(text, keywords):
    """Return character positions of subjective keywords in text."""
    positions = []
    for kw in keywords:
        idx = text.find(kw)
        while idx >= 0:
            positions.append(idx)
            idx = text.find(kw, idx + 1)
    return sorted(positions)

def score_claim(claim_text, keyword_positions, claim_start):
    """Score a claim's priority for verification. Higher = verify first."""
    score = 0
    # Factor 1: proximity to subjective keywords (closer = higher risk)
    if keyword_positions:
        min_dist = min(abs(claim_start - kp) for kp in keyword_positions)
        if min_dist < 50:
            score += 30
        elif min_dist < 100:
            score += 15
        elif min_dist < 200:
            score += 5
    # Factor 2: shorter claims are easier to verify
    if len(claim_text) < 30:
        score += 10
    elif len(claim_text) < 60:
        score += 5
    return score

def prioritize(text, keywords, max_claims=3):
    """Extract and score claims from text. Returns top N sorted by priority."""
    claims = extract_claims(text)
    kw_pos = find_keyword_positions(text, keywords)
    scored = []
    for claim in claims:
        start = text.find(claim)
        s = score_claim(claim, kw_pos, start)
        scored.append({"text": claim, "score": round(s, 2), "position": start})
    scored.sort(key=lambda x: x["score"], reverse=True)
    selected = scored[:max_claims]
    selected.sort(key=lambda x: x["position"])
    return selected
