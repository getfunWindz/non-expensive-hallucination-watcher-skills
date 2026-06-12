import json, re, sys
from pathlib import Path
from datetime import datetime

DEFAULT_COMPLEXITY = [
    {"keywords": ["\u4f60\u597d", "hello", "hi", "hey", "\u8c22\u8c22", "thanks", "bye", "\u518d\u89c1", "good"], "score": 500, "level": "chat"},
    {"keywords": ["\u4ec0\u4e48", "\u662f\u8c01", "\u5728\u54ea", "where", "when", "who", "what", "\u591a\u5c11\u94b1", "\u51e0\u70b9"], "score": 5000, "level": "simple_qa"},
    {"keywords": ["\u662f\u4ec0\u4e48", "\u4ec0\u4e48\u662f", "\u54ea\u4e2a", "how", "which", "tell me", "describe"], "score": 20000, "level": "factual"},
    {"keywords": ["\u4e3a\u4ec0\u4e48", "\u600e\u4e48", "\u539f\u56e0", "\u89e3\u91ca", "explain", "why", "how does", "how to"], "score": 100000, "level": "explanation"},
    {"keywords": ["\u5206\u6790", "\u6bd4\u8f83", "\u4f18\u7f3a\u70b9", "pros", "cons", "compare", "contrast", "\u5229\u5f0a", "\u533a\u522b", "\u5dee\u5f02", "different", "similarities"], "score": 300000, "level": "analysis"},
    {"keywords": ["\u7b97\u6cd5", "\u67b6\u6784", "\u4ee3\u7801", "code", "algorithm", "complexity", "\u51fd\u6570", "\u5b9e\u73b0", "implement", "design", "\u67b6\u6784\u8bbe\u8ba1", "\u7cfb\u7edf\u8bbe\u8ba1"], "score": 500000, "level": "technical"},
    {"keywords": ["\u8bc1\u660e", "\u63a8\u5bfc", "proof", "theorem", "derive", "formal", "deduce", "\u63a8\u7406", "\u8bba\u8bc1"], "score": 1000000, "level": "derivation"},
    {"keywords": ["\u8bba\u6587", "research", "methodology", "\u5b9e\u9a8c", "experiment", "novel", "contribution", "state of the art", "SOTA"], "score": 800000, "level": "academic"},
]

def estimate_thinking(question, topic_sig, params_path, thinking_multiplier=3.0):
    complexity_map = DEFAULT_COMPLEXITY
    keyword_to_score = {}
    keyword_to_level = {}
    for entry in complexity_map:
        for kw in entry["keywords"]:
            keyword_to_score[kw] = entry["score"]
            keyword_to_level[kw] = entry["level"]
    sig_score = 0
    sig_count = 0
    highest_level = "chat"
    level_order = ["chat", "simple_qa", "factual", "explanation", "analysis", "technical", "academic", "derivation"]
    if topic_sig:
        for kw, count in topic_sig.items():
            if kw in keyword_to_score:
                sig_score += keyword_to_score[kw] * count
                sig_count += count
                lvl = keyword_to_level.get(kw, "chat")
                if level_order.index(lvl) > level_order.index(highest_level): highest_level = lvl
    text_score = 0
    text_count = 0
    if question:
        q_lower = question.lower()
        for kw, sc in keyword_to_score.items():
            if len(kw) <= 2 and not any('\u4e00' <= c <= '\u9fff' for c in kw): continue
            if kw in q_lower:
                text_score += sc
                text_count += 1
                lvl = keyword_to_level.get(kw, "chat")
                if level_order.index(lvl) > level_order.index(highest_level): highest_level = lvl
    total_count = sig_count + text_count
    if total_count > 0:
        avg_score = (sig_score + text_score) / total_count
    else:
        q_len = len(question) if question else 0
        if q_len < 10: avg_score = 2000
        elif q_len < 50: avg_score = 10000
        elif q_len < 200: avg_score = 50000
        else: avg_score = 200000
    estimated = int(avg_score * max(thinking_multiplier, 0.1))
    return {"estimated_thinking": estimated, "complexity_score": round(avg_score, 0), "matched_level": highest_level, "thinking_multiplier": thinking_multiplier}

def main():
    data = json.loads(sys.stdin.read())
    mode = data.get("mode", "estimate")
    if mode == "estimate":
        result = estimate_thinking(data.get("question",""), data.get("topic_sig",{}), None, data.get("thinking_multiplier",3.0))
        print(json.dumps(result))

if __name__ == "__main__":
    main()
