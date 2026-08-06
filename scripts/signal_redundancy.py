#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
signal_redundancy.py — 冗余度信号。
随着对话轮次增加和累计文本量增长，冗余度线性增加。
用于在长对话中提高对重复内容的敏感度。
"""
import json, sys

def calc(total_text_len, params):
    tpi = params.get("redundancy_tokens_per_increment", 1000)
    inc = params.get("redundancy_increment", 5)
    cap = params.get("redundancy_max_score", 40)  # 上限：防止长对话必然触发 verify
    score = (total_text_len / tpi) * inc
    return round(min(score, cap), 2)

if __name__ == "__main__":
    stdin = sys.stdin.read().strip()
    if stdin:
        inp = json.loads(stdin)
        total_len = inp.get("total_text_len", 0)
        params = inp.get("params", {})
        score = calc(total_len, params)
        print(json.dumps({"redundancy_score": score}))
