#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
signal_consistency.py — 跨轮次自洽性检查（极简版）。
检测当前回复与上一轮回复之间的文本相似度。
极低相似度 + 相同话题 = 可能的自相矛盾（高风险）。
极高相似度 = 重复/冗余（中风险）。
"""
import sys, json, os, re

def extract_claims(text):
    """Extract assertion sentences as claims."""
    sents = re.split(r'[。！？\n]', text)
    claims = [s.strip() for s in sents if len(s.strip()) > 10]
    return claims

def jaccard_similarity(s1, s2):
    """Word-level Jaccard similarity."""
    w1 = set(re.findall(r'[\w]+', s1.lower()))
    w2 = set(re.findall(r'[\w]+', s2.lower()))
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / len(w1 | w2)

def check(text, prev_text, threshold_low=0.05, threshold_high=0.90):
    claims = extract_claims(text)
    prev_claims = extract_claims(prev_text) if prev_text else []
    if not prev_claims:
        return {"score": 0, "detail": "no previous turn for comparison"}
    if not claims:
        return {"score": 0, "detail": "no claims in current turn"}

    # Compare current claims against previous claims
    max_sim = 0
    min_sim = 1
    contradictions = []
    for c in claims:
        for p in prev_claims:
            sim = jaccard_similarity(c, p)
            max_sim = max(max_sim, sim)
            min_sim = min(min_sim, sim)

    score = 0
    detail = "consistent"
    if max_sim < threshold_low and len(claims) > 0 and len(prev_claims) > 0:
        score = 0.7  # suspiciously different
        detail = "very low similarity with previous turn"
    elif max_sim > threshold_high:
        score = 0.4  # too repetitive
        detail = "very high similarity with previous turn (repetition)"

    return {"score": score, "detail": detail, "max_sim": round(max_sim, 3), "min_sim": round(min_sim, 3)}

if __name__ == "__main__":
    stdin = sys.stdin.read().strip()
    if not stdin:
        print(json.dumps({"error": "no input"}))
        sys.exit(1)
    inp = json.loads(stdin)
    result = check(inp.get("text", ""), inp.get("prev_text", ""))
    print(json.dumps(result))
