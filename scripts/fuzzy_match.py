import hashlib
import difflib
import json
import sys


def extract_chars(text, conv_num, k=5):
    if not text:
        return ""
    seed = f"{text}{conv_num}"
    h = hashlib.sha256(seed.encode()).hexdigest()
    positions = [int(h[i*8:(i+1)*8], 16) % max(len(text), 1) for i in range(k)]
    chars = "".join(text[p] for p in sorted(positions))
    return chars


def fuzzy_similarity(a, b):
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def calc_fuzzy_score(similarity, base=50, multiplier=2.5):
    sim_pct = similarity * 100
    if sim_pct >= 80:
        return 0.0
    return max(float(base), (100 - sim_pct) * multiplier)


if __name__ == "__main__":
    try:
        data = json.loads(sys.stdin.read())
        mode = data.get("mode", "extract")

        if mode == "extract":
            text = data["text"]
            conv_num = data["conv_num"]
            k = data.get("k", 5)
            chars = extract_chars(text, conv_num, k)
            print(json.dumps({"chars": chars}))

        elif mode == "compare":
            chars_a = data["chars_a"]
            chars_b = data["chars_b"]
            sim = fuzzy_similarity(chars_a, chars_b)
            base = data.get("base", 50)
            multiplier = data.get("multiplier", 2.5)
            score = calc_fuzzy_score(sim, base, multiplier)
            print(json.dumps({
                "similarity": round(sim, 4),
                "similarity_pct": round(sim * 100, 2),
                "fuzzy_score": round(score, 2),
            }))

        elif mode == "record":
            from session_store import update_last_turn

            proj = data["project_dir"]
            sid = data["session_id"]
            updates = {
                "fuzzy_chars": data.get("chars"),
                "fuzzy_similarity": data.get("similarity"),
                "fuzzy_score": data.get("fuzzy_score"),
            }
            updates = {k: v for k, v in updates.items() if v is not None}
            if updates:
                update_last_turn(proj, sid, updates)
            print(json.dumps({"status": "recorded", "fields": list(updates.keys())}))

    except Exception as e:
        print(json.dumps({"error": str(e)}))
