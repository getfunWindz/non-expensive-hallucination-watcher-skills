import json, sys

def score_claim(ct, sp, cp, fs):
    score = 0
    if sp and cp is not None:
        md = min(abs(cp-s) for s in sp)
        if md<50: score+=30
        elif md<100: score+=15
        elif md<200: score+=5
    score += fs/10
    tl = len(ct) if ct else 0
    if tl<30: score+=10
    elif tl<60: score+=5
    return score

def select_claims(claims, mc=3):
    scored = sorted([{"text":c["text"],"score":score_claim(c.get("text",""),c.get("subjective_positions",[]),c.get("position"),c.get("fuzzy_score",0)),"position":c.get("position",0)} for c in claims], key=lambda x:x["score"], reverse=True)[:mc]
    scored.sort(key=lambda x:x["position"])
    return scored

def decide_method(h, p):
    ft = not h.get("correction_method")
    ba = h.get("b_path_accuracy",0.5)
    bm = p.get("b_path_min_accuracy",0.8)
    tp = p.get("token_usage_pct",0)
    if ft: return {"use_b":True,"use_a":True,"reason":"first_trigger"}
    if ba<bm: return {"use_b":False,"use_a":True,"reason":"b_path_unreliable"}
    if tp<80: return {"use_b":True,"use_a":True,"reason":"sufficient_budget"}
    return {"use_b":True,"use_a":False,"reason":"budget_saving"}

def main():
    d = json.loads(sys.stdin.read())
    m = d.get("mode","prioritize")
    if m=="prioritize": print(json.dumps({"selected":select_claims(d.get("claims",[]),d.get("max_claims",3))},ensure_ascii=False))
    elif m=="decide": print(json.dumps(decide_method(d.get("history",{}),d.get("params",{}))))

if __name__ == "__main__":
    main()
