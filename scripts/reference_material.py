import json, sys
from pathlib import Path
from datetime import datetime, timezone

def get_path(pd): return Path(pd)/"hallucination-watch"/"reference_material.json"

def main():
    d = json.loads(sys.stdin.read())
    m = d.get("mode","add")
    proj = d["project_dir"]
    path = get_path(proj)
    if path.exists():
        with open(path,"r",encoding="utf-8-sig") as f: mat = json.load(f)
    else: mat = {"entries":[],"last_updated":None}
    if m == "add":
        mat["entries"].append({"topic_sig":d.get("topic_sig",{}),"claims_text":d.get("claims_text","")[:1000],"timestamp":datetime.now(timezone.utc).isoformat()})
        mat["last_updated"] = datetime.now(timezone.utc).isoformat()
        with open(path,"w",encoding="utf-8") as f: json.dump(mat,f,indent=2,ensure_ascii=False)
        print(json.dumps({"status":"added","total":len(mat["entries"])}))
    elif m == "check":
        if not mat["entries"]:
            print(json.dumps({"status":"no_material","material_inconsistency":0})); return
        cs = d.get("current_sig",{}); scs = set(cs.keys())
        if not scs: print(json.dumps({"status":"no_sig","material_inconsistency":0})); return
        matches = sum(1 for e in mat["entries"] if len(set(e.get("topic_sig",{}).keys())&scs)/max(len(set(e.get("topic_sig",{}).keys())|scs),1)>=d.get("threshold",0.15))
        print(json.dumps({"status":"checked" if matches>0 else "no_match","material_inconsistency":max(0,40-matches*8),"matches":matches}))

if __name__ == "__main__":
    main()
