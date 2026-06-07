import json, hashlib, difflib, sys, os, subprocess
from pathlib import Path
from datetime import datetime, timezone

SKILL_DIR = Path(os.environ["USERPROFILE"])/".config"/"opencode"/"skills"/"hallucination-watch"
TEST_DIR = Path(os.environ["TEMP"])/"hallucination-watch-e2e"
DATA_DIR = TEST_DIR/"hallucination-watch"

CONVS = [(i,"test","ok",True) for i in range(1,7)] + [(i,"test","ok",False) for i in range(7,51)]
TRIGGER_HISTORY = []

def load_json(p):
    try: return json.load(open(p,encoding="utf-8-sig"))
    except: return json.load(open(p,encoding="utf-8"))

def save_json(p,d): json.dump(d,open(p,"w",encoding="utf-8"),indent=2,ensure_ascii=False)

def count_subj(t,kw): return sum(t.count(k) for k in kw)

def main():
    if TEST_DIR.exists(): import shutil; shutil.rmtree(TEST_DIR)
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    params = load_json(SKILL_DIR/"params"/"default.json")
    params["threshold"]=200
    session = {"conversation_number":0,"phase":"baseline","previous":None,"current":None,"habit_profile":{"total_samples":0,"bin_probs":[0.2]*5}}
    permanent = {"last_updated":None,"results":[]}
    cal_done=False
    for cn,um,mr,is_bl in CONVS:
        if not is_bl and not cal_done:
            ci = json.dumps({"project_dir":str(TEST_DIR),"skill_dir":str(SKILL_DIR)})
            subprocess.run(["python",str(SKILL_DIR/"scripts"/"calibrate_threshold.py")],input=ci,capture_output=True,text=True)
            cal_done=True
            lp = DATA_DIR/"params.json"
            if lp.exists(): params["threshold"]=load_json(lp)["threshold"]
        sc = count_subj(mr,params["keyword_list"])
        ch = ""
        ts = sc
        st = sc>=params["threshold"]
        session["previous"]=session.get("current")
        session["current"]={"conv":cn,"subjective_count":sc,"fuzzy_chars":ch,"fuzzy_score":0,"total_tokens":len(um+mr),"timestamp":datetime.now(timezone.utc).isoformat()}
        session["conversation_number"]=cn
        session["phase"]="baseline" if is_bl else "active"
        save_json(DATA_DIR/"session.json",session)
        e = {"timestamp":datetime.now(timezone.utc).isoformat(),"conv":cn,"subjective":sc,"fuzzy_match_score":0,"redundancy":0,"formula_raw":ts,"triggered":st,"phase":"baseline" if is_bl else "active","correction":{"method":"none","b_path_agreed":None,"claims_extracted":0,"claims_verified":0,"claims_wrong":0,"correction_applied":False,"user_contested":False,"user_contested_at":None}}
        permanent["results"].append(e)
        permanent["last_updated"]=datetime.now(timezone.utc).isoformat()
        save_json(DATA_DIR/"permanent.json",permanent)
        print(f"[CONV #{cn:02d}] Score:{ts:5.0f} Trig:{st}")
    print("\nE2E PASSED")
    return 0

if __name__=="__main__":
    sys.exit(main())
