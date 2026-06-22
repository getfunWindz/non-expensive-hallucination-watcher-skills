"""
compare_models.py — Multi-model hallucination risk comparison tool.

Runs the same set of questions through the detection pipeline for each model,
then outputs a side-by-side comparison report.

Usage:
  python compare_models.py <questions.json> <model_a.json> [model_b.json ...]

Input:
  questions.json:  [{"id":1,"question":"...","answer":"..."}, ...]
  model_*.json:    [{"id":1,"response":"..."}, ...] (one per model)

Output:
  Prints a formatted comparison table to stdout.
"""
import json
import hashlib
import difflib
import sys
from pathlib import Path


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except json.JSONDecodeError:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


def count_subjective(text, keywords):
    return sum(text.count(kw) for kw in keywords)


def extract_chars(text, conv_num, k=5):
    if not text:
        return ""
    seed = f"{text}{conv_num}"
    h = hashlib.sha256(seed.encode()).hexdigest()
    positions = [int(h[i*8:(i+1)*8], 16) % max(len(text), 1) for i in range(k)]
    return "".join(text[p] for p in sorted(positions))


def fuzzy_similarity(a, b):
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def calc_fuzzy_score(sim_pct, base=50, multiplier=2.5):
    if sim_pct >= 80:
        return 0.0
    return max(float(base), (100 - sim_pct) * multiplier)


KEYWORDS = ["一定", "绝对是", "肯定", "必然", "毫无疑问",
            "必须", "不可能", "总是", "永远", "从来都",
            "绝不", "一定不会", "肯定不", "绝对不"]


def analyze_responses(questions, responses, label, k=5):
    """Run detection pipeline over all responses for one model."""
    results = []
    total_raw = 0
    total_subj = 0
    total_fuzzy = 0

    for i, entry in enumerate(responses):
        q = next((q for q in questions if q["id"] == entry["id"]), None)
        if not q:
            continue

        conv_num = entry["id"]
        resp = entry["response"]

        subj = count_subjective(resp, KEYWORDS)
        chars = extract_chars(resp, conv_num, k)

        fuzzy_score = 0
        if i > 0:
            prev_resp = responses[i - 1]["response"]
            prev_chars = extract_chars(prev_resp, conv_num - 1, k)
            sim = fuzzy_similarity(chars, prev_chars) * 100
            fuzzy_score = calc_fuzzy_score(sim)

        raw = subj + fuzzy_score

        results.append({
            "id": conv_num,
            "question": q.get("question", ""),
            "subjective": subj,
            "fuzzy_score": round(fuzzy_score, 2),
            "formula_raw": round(raw, 2),
            "chars": chars
        })
        total_raw += raw
        total_subj += subj
        total_fuzzy += fuzzy_score

    n = len(results)
    return {
        "label": label,
        "n": n,
        "avg_raw": round(total_raw / n, 2) if n else 0,
        "avg_subjective": round(total_subj / n, 2) if n else 0,
        "avg_fuzzy": round(total_fuzzy / n, 2) if n else 0,
        "results": results
    }


def print_report(analyses):
    """Print side-by-side comparison report."""
    labels = [a["label"] for a in analyses]

    # Summary header
    print("=" * 80)
    print("MULTI-MODEL HALLUCINATION RISK COMPARISON")
    print("=" * 80)
    print()
    print(f"{'Metric':<25}", end="")
    for l in labels:
        print(f"{l:<20}", end="")
    print()
    print("-" * 25 + "+" + "-" * (20 * len(labels) - 1))

    print(f"{'Conversations':<25}", end="")
    for a in analyses:
        print(f"{a['n']:<20}", end="")
    print()

    print(f"{'Avg Formula Raw':<25}", end="")
    for a in analyses:
        print(f"{a['avg_raw']:<20}", end="")
    print()

    print(f"{'Avg Subjective':<25}", end="")
    for a in analyses:
        print(f"{a['avg_subjective']:<20}", end="")
    print()

    print(f"{'Avg Fuzzy Score':<25}", end="")
    for a in analyses:
        print(f"{a['avg_fuzzy']:<20}", end="")
    print()

    print()
    print("=" * 80)
    print("PER-QUESTION DETAIL")
    print("=" * 80)

    num_questions = max(a["n"] for a in analyses)
    for qi in range(num_questions):
        print()
        q_text = analyses[0]["results"][qi]["question"] if qi < analyses[0]["n"] else ""
        print(f"Q{qi + 1}: {q_text[:60]}")
        print(f"{'Model':<20} {'Subj':<8} {'Fuzzy':<10} {'Raw':<10} {'Chars':<12}")
        print("-" * 60)
        for a in analyses:
            if qi < a["n"]:
                r = a["results"][qi]
                print(f"{a['label']:<20} {r['subjective']:<8} {r['fuzzy_score']:<10} "
                      f"{r['formula_raw']:<10} {r['chars']:<12}")

    # Best-model recommendation
    print()
    print("=" * 80)
    best = min(analyses, key=lambda a: a["avg_raw"])
    print(f"RECOMMENDATION: '{best['label']}' has lowest avg hallucination risk "
          f"({best['avg_raw']})")
    print("=" * 80)


def main():
    if len(sys.argv) < 3:
        print("Usage: python compare_models.py <questions.json> <model_a.json> [model_b.json ...]")
        sys.exit(1)

    questions = load_json(sys.argv[1])
    model_files = sys.argv[2:]

    analyses = []
    for f in model_files:
        label = Path(f).stem
        responses = load_json(f)
        analysis = analyze_responses(questions, responses, label)
        analyses.append(analysis)

    print_report(analyses)


if __name__ == "__main__":
    main()
