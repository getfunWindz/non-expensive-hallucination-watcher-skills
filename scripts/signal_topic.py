#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
signal_topic.py — 话题嵌入（jieba 分词 + 停用词过滤）。

从文本中提取关键词作为话题签名，集成原版 topic_embed.py 的停用词表。
供 signal_material.py 做话题门控。
"""
import re, json, sys
import jieba

jieba.initialize()

_STOP_WORDS = {
    "what", "is", "the", "how", "does", "do", "a", "an", "in", "of", "to",
    "and", "or", "for", "on", "with", "at", "by", "this", "that", "it",
    "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "not", "no", "but", "so", "if", "as", "all", "can", "will", "would",
    "could", "should", "may", "might", "about", "into", "through", "during",
    "什么", "怎么", "为什么", "如何", "哪些", "哪个", "没有",
    "自己", "我们", "你们", "他们", "她们", "它们", "一个",
    "的", "是", "了", "在", "有", "和", "就", "不", "人",
    "都", "一", "上", "也", "很", "到", "说", "要", "去",
    "你", "会", "着", "看", "好", "这", "那", "他", "她",
    "它", "们", "我", "吧", "吗", "啊", "呢", "噢", "哦",
    "嗯", "呗", "啦", "哟", "呀", "哇", "呵", "哈", "喂",
    "与", "或", "及", "但", "可", "被", "把", "对", "从",
    "以", "而", "所", "为", "因", "由", "于", "向", "让",
    "比", "按", "照", "凭", "沿", "顺", "朝", "往", "跟",
    "同", "除", "之", "间", "其", "中", "前", "后", "内",
    "外", "旁", "左", "右", "东", "西", "南", "北",
    "每", "各", "几", "多", "少", "全", "半",
    "能", "够", "应", "该", "需", "要", "必",
    "须", "愿", "意", "想", "要", "希", "望",
    "ai", "a", "an", "the", "this", "that",
}

def extract(text, top_n=8):
    """Extract topic signature as {word: count} dict, top_n by frequency.
    
    Uses jieba for Chinese word segmentation + stop word filtering.
    """
    words = jieba.lcut(text)
    freq = {}
    for w in words:
        w = w.strip().lower()
        if len(w) < 2:
            continue
        if re.match(r'^\d+$', w):
            continue
        if w in _STOP_WORDS:
            continue
        freq[w] = freq.get(w, 0) + 1
    # Also include English terms not captured by jieba
    eng = re.findall(r'[a-zA-Z]+', text)
    for e in eng:
        e_lower = e.lower()
        if len(e_lower) >= 2 and e_lower not in _STOP_WORDS:
            freq[e_lower] = freq.get(e_lower, 0) + 1
    sorted_w = sorted(freq.items(), key=lambda x: -x[1])
    return {k: v for k, v in sorted_w[:top_n]}

def similarity(sig_a, sig_b):
    """Jaccard similarity based on word overlap."""
    if not sig_a or not sig_b:
        return 0.0
    set_a = set(sig_a.keys())
    set_b = set(sig_b.keys())
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)

if __name__ == "__main__":
    stdin = sys.stdin.read().strip()
    if stdin:
        inp = json.loads(stdin)
        sig = extract(inp.get("text", ""), inp.get("top_n", 8))
        print(json.dumps(sig, ensure_ascii=False))
