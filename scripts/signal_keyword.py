import sys, json, re

def detect(text, params):
    if isinstance(params, str):
        import json; params = json.loads(params)
    kw_list = params.get("keywords", [])
    rf_list = params.get("red_flag_keywords", [])
    mult = params.get("density_multiplier", 10)
    total_chars = max(len(text), 1)
    matched = []
    score = 0
    for kw in kw_list:
        c = text.count(kw)
        if c:
            matched.append({"keyword": kw, "count": c})
            score += c * mult
    red_flags = []
    for rf in rf_list:
        c = text.count(rf)
        if c:
            red_flags.append({"keyword": rf, "count": c})
            score += c * mult * 3
    return {"density": round(score / total_chars, 4), "matched": matched, "red_flags": red_flags}
