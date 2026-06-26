import sys, json, re, hashlib

def extract_fingerprint(text, k=7):
    chars = []
    sents = re.split(r'[\uff0e\uff01\uff1f\n]', text)
    for s in sents:
        s = s.strip()
        if s: chars.append(s[0])
    for c in text:
        if c.isdigit() or c.isalpha():
            chars.append(c)
            if len(chars) >= k * 2: break
    return ''.join(chars[:k])

def compare(prev_fp, curr_fp):
    if not prev_fp or not curr_fp: return 0.0, 0
    shared = sum(1 for a, b in zip(prev_fp, curr_fp) if a == b)
    max_len = max(len(prev_fp), len(curr_fp))
    similarity = shared / max_len if max_len > 0 else 0
    return round(similarity, 3), round((1 - similarity) * 10, 2)

def process(text, prev_text, k=7):
    curr_fp = extract_fingerprint(text, k)
    prev_fp = extract_fingerprint(prev_text, k) if prev_text else ""
    similarity, score = compare(prev_fp, curr_fp) if prev_fp else (0.0, 0)
    return {"fingerprint": curr_fp, "similarity": similarity, "score": score}
