import sys, json, re

def extract_claims(text):
    sents = re.split(r'[\uff0e\uff01\uff1f\n]', text)
    return [s.strip() for s in sents if len(s.strip()) > 10]

def jaccard_similarity(s1, s2):
    w1 = set(re.findall(r'[\w]+', s1.lower()))
    w2 = set(re.findall(r'[\w]+', s2.lower()))
    if not w1 or not w2: return 0.0
    return len(w1 & w2) / len(w1 | w2)

def check(text, prev_text, threshold_low=0.05, threshold_high=0.90):
    claims = extract_claims(text)
    prev_claims = extract_claims(prev_text) if prev_text else []
    if not prev_claims:
        return {"score": 0, "detail": "no previous turn"}
    if not claims:
        return {"score": 0, "detail": "no claims"}
    max_sim = max(jaccard_similarity(c, p) for c in claims for p in prev_claims) or 0
    score = 0.7 if max_sim < threshold_low else (0.4 if max_sim > threshold_high else 0)
    detail = "very low similarity" if max_sim < threshold_low else ("high repetition" if max_sim > threshold_high else "consistent")
    return {"score": score, "detail": detail, "max_sim": round(max_sim, 3)}
