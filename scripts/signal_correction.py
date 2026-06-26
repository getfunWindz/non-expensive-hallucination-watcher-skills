import sys, json, re

def extract_claims(text):
    return [s.strip() for s in re.split(r'[\uff0e\uff01\uff1f\n]', text) if len(s.strip()) >= 8]

def find_keyword_positions(text, keywords):
    positions = []
    for kw in keywords:
        idx = text.find(kw)
        while idx >= 0: positions.append(idx); idx = text.find(kw, idx + 1)
    return sorted(positions)

def score_claim(claim, kw_positions, start):
    score = 0
    if kw_positions:
        min_dist = min(abs(start - kp) for kp in kw_positions)
        if min_dist < 50: score += 30
        elif min_dist < 100: score += 15
        elif min_dist < 200: score += 5
    if len(claim) < 30: score += 10
    elif len(claim) < 60: score += 5
    return score

def prioritize(text, keywords, max_claims=3):
    claims = extract_claims(text)
    kw_pos = find_keyword_positions(text, keywords)
    scored = [{"text": c, "score": round(score_claim(c, kw_pos, text.find(c)), 2), "position": text.find(c)} for c in claims]
    scored.sort(key=lambda x: x["score"], reverse=True)
    selected = sorted(scored[:max_claims], key=lambda x: x["position"])
    return selected
