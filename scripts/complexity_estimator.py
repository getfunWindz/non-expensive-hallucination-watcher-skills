"""
complexity_estimator.py — Question complexity → thinking token estimator.

Estimates the amount of thinking tokens a model will generate
to answer a question, based on the question's topic complexity.

Two modes:
  estimate:  Given question text + topic_sig → estimated thinking tokens
  calibrate: Given user_contested topic_sig → adjust complexity score

The complexity map is stored in params.json and persists across sessions.
"""
import json
import re
import sys
from pathlib import Path
from datetime import datetime


# Default complexity map: keyword → thinking tokens per occurrence
# Values based on observed behavior: simple Q&A ~few K, deep reasoning ~1M+
DEFAULT_COMPLEXITY = [
    # Simple chat / social (minimal thinking)
    {"keywords": ["你好", "hello", "hi", "hey", "谢谢", "thanks", "bye", "再见", "good"], "score": 500, "level": "chat"},
    # Simple factual lookup (low thinking)
    {"keywords": ["什么", "是谁", "在哪", "where", "when", "who", "what", "多少钱", "几点"], "score": 5000, "level": "simple_qa"},
    # Factual explanation (moderate thinking)
    {"keywords": ["是什么", "什么是", "哪个", "how", "which", "tell me", "describe"], "score": 20000, "level": "factual"},
    # Causal / explanatory (substantial thinking)
    {"keywords": ["为什么", "怎么", "原因", "解释", "explain", "why", "how does", "how to"], "score": 100000, "level": "explanation"},
    # Analytical (heavy thinking)
    {"keywords": ["分析", "比较", "优缺点", "pros", "cons", "compare", "contrast", "利弊",
                  "区别", "差异", "different", "similarities"], "score": 300000, "level": "analysis"},
    # Technical / code (very heavy thinking)
    {"keywords": ["算法", "架构", "代码", "code", "algorithm", "complexity", "函数",
                  "实现", "implement", "design", "架构设计", "系统设计"], "score": 500000, "level": "technical"},
    # Derivation / proof (maximum thinking)
    {"keywords": ["证明", "推导", "proof", "theorem", "derive", "formal", "deduce",
                  "推理", "论证"], "score": 1000000, "level": "derivation"},
    # Academic / research (very heavy)
    {"keywords": ["论文", "research", "methodology", "实验", "experiment", "novel",
                  "contribution", "state of the art", "SOTA"], "score": 800000, "level": "academic"},
]


def load_map(params_path):
    """Load complexity map from params.json, or use defaults."""
    if params_path and params_path.exists():
        with open(params_path, "r", encoding="utf-8") as f:
            p = json.load(f)
        return p.get("complexity_map", DEFAULT_COMPLEXITY)
    return DEFAULT_COMPLEXITY


def save_map(params_path, complexity_map):
    """Persist updated complexity map."""
    if params_path and params_path.exists():
        with open(params_path, "r", encoding="utf-8") as f:
            p = json.load(f)
    else:
        p = {}
    p["complexity_map"] = complexity_map
    with open(params_path, "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2, ensure_ascii=False)


def estimate_thinking(question, topic_sig, params_path, thinking_multiplier=3.0):
    """
    Estimate thinking tokens for a question based on its topic complexity.

    Args:
        question: Raw question text
        topic_sig: Dict of {keyword: count} from topic_embed.py
        thinking_multiplier: Fallback multiplier if no topic match

    Returns:
        dict with estimated_thinking, complexity_score, matched_level
    """
    complexity_map = load_map(params_path)

    if not question and not topic_sig:
        return {"estimated_thinking": 0, "complexity_score": 0, "matched_level": "none"}

    # Build reverse lookup: keyword → score
    keyword_to_score = {}
    keyword_to_level = {}
    for entry in complexity_map:
        for kw in entry["keywords"]:
            keyword_to_score[kw] = entry["score"]
            keyword_to_level[kw] = entry["level"]

    # Score from topic_sig (Chinese keywords)
    sig_score = 0
    sig_count = 0
    matched_keywords = []
    highest_level = "chat"

    if topic_sig:
        for kw, count in topic_sig.items():
            if kw in keyword_to_score:
                sig_score += keyword_to_score[kw] * count
                sig_count += count
                matched_keywords.append(kw)
                lvl = keyword_to_level.get(kw, "chat")
                # Track highest level
                level_order = ["chat", "simple_qa", "factual", "explanation",
                              "analysis", "technical", "academic", "derivation"]
                if level_order.index(lvl) > level_order.index(highest_level):
                    highest_level = lvl

    # Score from raw question text (Chinese + English keywords)
    text_score = 0
    text_count = 0
    if question:
        q_lower = question.lower()
        for kw, sc in keyword_to_score.items():
            # Skip very short English-only keywords (a, in, of), but keep Chinese 2-char keywords
            if len(kw) <= 2 and not any('\u4e00' <= c <= '\u9fff' for c in kw):
                continue
            if kw in q_lower:
                text_score += sc
                text_count += 1
                lvl = keyword_to_level.get(kw, "chat")
                level_order = ["chat", "simple_qa", "factual", "explanation",
                              "analysis", "technical", "academic", "derivation"]
                if level_order.index(lvl) > level_order.index(highest_level):
                    highest_level = lvl

    # Average score
    total_count = sig_count + text_count
    if total_count > 0:
        avg_score = (sig_score + text_score) / total_count
    else:
        # No keywords matched — use base fallback based on question length
        q_len = len(question) if question else 0
        if q_len < 10:
            avg_score = 2000
            highest_level = "chat"
        elif q_len < 50:
            avg_score = 10000
            highest_level = "simple_qa"
        elif q_len < 200:
            avg_score = 50000
            highest_level = "factual"
        else:
            avg_score = 200000
            highest_level = "analysis"

    # Scale by thinking_multiplier (configurable)
    estimated = int(avg_score * max(thinking_multiplier, 0.1))

    return {
        "estimated_thinking": estimated,
        "complexity_score": round(avg_score, 0),
        "matched_level": highest_level,
        "keyword_matches": matched_keywords[:5],
        "thinking_multiplier": thinking_multiplier
    }


def calibrate(topic_sig, adjustment, params_path):
    """
    Calibrate complexity map based on user feedback.
    adjustment > 1.0 = increase complexity (user contested, model under-thought)
    adjustment < 1.0 = decrease complexity (overthinking simple questions)
    """
    complexity_map = load_map(params_path)
    if not topic_sig:
        # No topic to calibrate against — adjust all levels slightly
        for entry in complexity_map:
            entry["score"] = int(entry["score"] * adjustment)
    else:
        # Adjust levels matching the topic
        for kw in topic_sig:
            for entry in complexity_map:
                if kw in entry["keywords"]:
                    entry["score"] = int(entry["score"] * adjustment)

    save_map(params_path, complexity_map)
    return {"status": "calibrated", "adjustment": adjustment}


def main():
    data = json.loads(sys.stdin.read())
    mode = data.get("mode", "estimate")
    project_dir = data.get("project_dir", "")
    params_path = Path(project_dir) / "hallucination-watch" / "params.json" if project_dir else None

    if mode == "estimate":
        result = estimate_thinking(
            data.get("question", ""),
            data.get("topic_sig", {}),
            params_path,
            data.get("thinking_multiplier", 3.0)
        )
        print(json.dumps(result))

    elif mode == "calibrate":
        result = calibrate(
            data.get("topic_sig", {}),
            data.get("adjustment", 1.2),
            params_path
        )
        print(json.dumps(result))


if __name__ == "__main__":
    main()
