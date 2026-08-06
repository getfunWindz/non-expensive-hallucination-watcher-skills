#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
signal_material.py — 参考素材一致性检查（集成话题嵌入）。

功能：
  1. 从当前文本中提取断言式句子作为"事实声明"
  2. 使用 signal_topic 提取话题签名，与 reference.json 中的历史声明做话题门控对比
  3. 仅话题相似度超过阈值时，才检查新旧声明是否存在矛盾
  4. 将新声明存入 reference.json
"""
import re, json, sys, os, datetime, hashlib
from signal_topic import extract as topic_extract, similarity as topic_similarity

TOPIC_THRESHOLD = 0.15
MAX_REFERENCE_ENTRIES = 50  # 条目上限：防止长会话中 reference.json 无限增长

# 声明提取触发词：必须与 has_contradiction 的矛盾对正面词保持一致，
# 否则「支持/不支持」这类矛盾永远检测不到。
CLAIM_TRIGGERS = ['是', '有', '可以', '能够', '将', '会', '已经', '支持', '具备', '完成', '尚未', '存在']

def extract_claims(text):
    sents = re.split(r'[。！？\n]', text)
    claims = []
    for s in sents:
        s = s.strip()
        if len(s) >= 8 and any(kw in s for kw in CLAIM_TRIGGERS):
            claims.append(s)
    return claims

def has_contradiction(new_claim, old_claim):
    new_lower = new_claim.lower()
    old_lower = old_claim.lower()
    pairs = [
        ('可以', '不可以'), ('能够', '不能够'), ('有', '没有'), ('是', '不是'),
        ('会', '不会'), ('已经', '尚未'), ('将', '不会'),
        ('支持', '不支持'), ('具备', '不具备'), ('完成', '未完成'),
    ]
    for pos, neg in pairs:
        if pos in new_lower and neg in old_lower:
            return True
        if neg in new_lower and pos in old_lower:
            return True
    return False

def check(text, reference_entries, topic_threshold=TOPIC_THRESHOLD):
    """Check text against reference entries with topic gating."""
    claims = extract_claims(text)
    text_topic = topic_extract(text, 5)
    if not claims or not reference_entries:
        return {"score": 0, "detail": "insufficient data", "claims_count": len(claims), "contradictions": 0}

    contradictions = 0
    total_checks = 0
    for claim in claims:
        claim_topic = topic_extract(claim, 3)
        for entry in reference_entries:
            entry_topic = entry.get("topic", {})
            # Topic gate: only check if topics are similar enough
            if topic_similarity(claim_topic, entry_topic) < topic_threshold:
                continue
            for ec in entry.get("claims", []):
                total_checks += 1
                if has_contradiction(claim, ec):
                    contradictions += 1

    score = (contradictions / max(total_checks, 1)) * 10
    return {
        "score": round(score, 2),
        "detail": f"{contradictions} contradictions in {total_checks} checks" if contradictions else "consistent",
        "claims_count": len(claims),
        "contradictions": contradictions
    }

def add_entry(entries, text):
    claims = extract_claims(text)
    topic = topic_extract(text, 5)
    if claims:
        fp = hashlib.md5(text.encode('utf-8')).hexdigest()[:16]
        # 与最近一条声明同文本时跳过（去重，避免同轮/重复回复反复入库）
        if entries and entries[-1].get("fp") == fp:
            return entries
        entries.append({
            "claims": claims,
            "topic": topic,
            "fp": fp,
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
        # 上限：保留最近 MAX_REFERENCE_ENTRIES 条（滑动窗口）
        if len(entries) > MAX_REFERENCE_ENTRIES:
            entries = entries[-MAX_REFERENCE_ENTRIES:]
    return entries

if __name__ == "__main__":
    stdin = sys.stdin.read().strip()
    if stdin:
        inp = json.loads(stdin)
        if inp.get("mode") == "add":
            with open(inp["reference_path"], encoding='utf-8') as f:
                ref = json.load(f)
            ref["entries"] = add_entry(ref.get("entries", []), inp.get("text", ""))
            ref["last_updated"] = datetime.datetime.utcnow().isoformat()
            with open(inp["reference_path"], 'w', encoding='utf-8') as f:
                json.dump(ref, f, ensure_ascii=False, indent=2)
            print(json.dumps({"status": "added"}))
        elif inp.get("mode") == "check":
            with open(inp.get("reference_path", ""), encoding='utf-8') as f:
                ref = json.load(f)
            result = check(inp.get("text", ""), ref.get("entries", []),
                          topic_threshold=inp.get("threshold", TOPIC_THRESHOLD))
            print(json.dumps(result))
