#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
signal_fuzzy.py — 模糊哈希匹配。
从文本中提取 k 个特征字符，跨轮比较相似度。
特征字符选择策略：取每个句子首字符 + 数字/英文首字符，形成紧凑指纹。
"""
import re, hashlib, json, sys

def extract_fingerprint(text, k=7):
    """Extract k-character fingerprint from text."""
    chars = []
    # Add first char of each sentence
    sents = re.split(r'[。！？\n]', text)
    for s in sents:
        s = s.strip()
        if s:
            chars.append(s[0])
    # Add first digit/letter found
    for c in text:
        if c.isdigit() or c.isalpha():
            chars.append(c)
            if len(chars) >= k * 2:
                break
    # Take first k chars
    fingerprint = ''.join(chars[:k])
    return fingerprint

def hash_fingerprint(fp):
    """Hash fingerprint to a compact hex string."""
    return hashlib.md5(fp.encode('utf-8')).hexdigest()[:8]

def compare(prev_fp, curr_fp):
    """Compare two fingerprints. Returns similarity (0-1) and score.

    降权设计（修复灵敏度）：只在「部分相似」（0.3~0.7）时计分。
    - 完全无关（<0.3）：正常话题变化，不计分
    - 部分相似（0.3~0.7）：模糊重叠，可疑，计分
    - 高度重复（>0.7）：重复由 consistency 信号负责，不计分
    """
    if not prev_fp or not curr_fp:
        return 0.0, 0
    # Character overlap similarity
    shared = sum(1 for a, b in zip(prev_fp, curr_fp) if a == b)
    max_len = max(len(prev_fp), len(curr_fp))
    similarity = shared / max_len if max_len > 0 else 0
    # Score: only partial similarity (0.3~0.7) is suspicious
    if 0.3 <= similarity <= 0.7:
        score = (1 - similarity) * 10
    else:
        score = 0.0
    return round(similarity, 3), round(score, 2)

def process(text, prev_text, k=7):
    """Full fuzzy match pipeline."""
    curr_fp = extract_fingerprint(text, k)
    prev_fp = extract_fingerprint(prev_text, k) if prev_text else ""
    curr_hash = hash_fingerprint(curr_fp)
    prev_hash = hash_fingerprint(prev_fp) if prev_fp else ""
    similarity = 0.0
    score = 0
    if prev_hash:
        similarity, score = compare(prev_fp, curr_fp)
    return {
        "fingerprint": curr_fp,
        "fingerprint_hash": curr_hash,
        "prev_hash": prev_hash,
        "similarity": similarity,
        "score": score
    }

if __name__ == "__main__":
    stdin = sys.stdin.read().strip()
    if stdin:
        inp = json.loads(stdin)
        result = process(inp.get("text", ""), inp.get("prev_text", ""), inp.get("k", 7))
        print(json.dumps(result))
