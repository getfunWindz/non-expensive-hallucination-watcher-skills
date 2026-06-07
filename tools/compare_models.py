import json, hashlib, difflib, sys
from pathlib import Path

def load_json(p):
    try: return json.load(open(p,encoding="utf-8-sig"))
    except: return json.load(open(p,encoding="utf-8"))

KW = ["一定","绝对是","肯定","必然","毫无疑问","必须","不可能","总是","永远","从来都","绝不","一定不会","肯定不","绝对不"]

def analyze(qs, res, label):
    results = []
    tr, ts, tf = 0,0,0
    for i,e in enumerate(res):
        q = next((x for x in qs if x["id"]==e["id"]), None)
        if not q: continue
        subj = sum(e["response"].count(k) for k in KW)
        chars = "".join(hashlib.sha256(f"{e['response']}{e['id']}".encode()).hexdigest() for _ in range(5))[:5]
        fuzzy = 0
        if i>0:
            pc = "".join(hashlib.sha256(f"{res[i-1]['response']}{e['id']-1}".encode()).hexdigest() for _ in range(5))[:5]
            s = difflib.SequenceMatcher(None,chars,pc).ratio()*100
            fuzzy = 0 if s>=80 else max(50,(100-s)*2.5)
        raw = subj+fuzzy
        results.append({"id":e["id"],"question":q.get("question",""),"subjective":subj,"fuzzy_score":round(fuzzy,2),"formula_raw":round(raw,2)})
        tr+=raw; ts+=subj; tf+=fuzzy
    n=len(results)
    return {"label":label,"n":n,"avg_raw":round(tr/n,2) if n else 0,"avg_subjective":round(ts/n,2) if n else 0,"avg_fuzzy":round(tf/n,2) if n else 0,"results":results}

def main():
    if len(sys.argv)<3: print("Usage: python compare_models.py <questions.json> <model_a.json> [model_b.json ...]"); sys.exit(1)
    qs = load_json(sys.argv[1])
    ans = [analyze(qs,load_json(f),Path(f).stem) for f in sys.argv[2:]]
    print("="*80)
    print("MULTI-MODEL HALLUCINATION RISK COMPARISON")
    print("="*80)
    for a in ans:
        print(f"{a['label']:>15} | AvgRaw: {a['avg_raw']:<8} AvgSubj: {a['avg_subjective']} AvgFuzzy: {a['avg_fuzzy']}")
    best = min(ans,key=lambda a:a["avg_raw"])
    print(f"\nRECOMMENDATION: '{best['label']}' (lowest avg risk: {best['avg_raw']})")

if __name__ == "__main__":
    main()
