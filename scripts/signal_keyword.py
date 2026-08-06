#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
signal_keyword.py — 关键词密度监测信号。
输入：当前回复文本
输出：keyword_density（浮点）, matched_keywords（列表）, red_flags（列表）
"""
import sys, json, os

def detect(text, params):
    opts = json.loads(params) if isinstance(params, str) else params
    kw_list = opts.get("keywords", [])
    rf_list = opts.get("red_flag_keywords", [])

    text_lower = text.lower()
    total_chars = max(len(text), 1)

    matched = []
    raw_score = 0  # 未乘 multiplier 的原始加权计数：普通词×1，红旗词×3
    for kw in kw_list:
        c = text_lower.count(kw.lower())
        if c:
            matched.append({"keyword": kw, "count": c})
            raw_score += c

    red_flags = []
    for rf in rf_list:
        c = text_lower.count(rf.lower())
        if c:
            red_flags.append({"keyword": rf, "count": c})
            raw_score += c * 3  # red flags weighted 3x

    # density = 加权计数 / 文本长度（不含 multiplier；multiplier 由调用方乘以）
    density = raw_score / total_chars
    return {"density": round(density, 4), "matched": matched, "red_flags": red_flags}

if __name__ == "__main__":
    stdin = sys.stdin.read().strip()
    if not stdin:
        print(json.dumps({"error": "no input"}))
        sys.exit(1)
    try:
        inp = json.loads(stdin)
    except json.JSONDecodeError:
        inp = {"text": stdin}
    with open(os.path.join(os.path.dirname(__file__), "..", "params", "default.json")) as f:
        params = json.load(f)
    result = detect(inp.get("text", ""), params)
    print(json.dumps(result))
