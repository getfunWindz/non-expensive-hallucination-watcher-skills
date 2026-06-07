import hashlib, difflib, json, sys

def extract_chars(text, conv_num, k=5):
    if not text: return ""
    h = hashlib.sha256(f"{text}{conv_num}".encode()).hexdigest()
    return "".join(text[int(h[i*8:(i+1)*8],16)%len(text)] for i in range(k))

def calc_fuzzy_score(sim, base=50, mul=2.5):
    p = sim*100
    if p>=80: return 0.0
    return max(float(base), (100-p)*mul)

def main():
    d = json.loads(sys.stdin.read())
    if d.get("mode")=="extract":
        c = extract_chars(d["text"],d["conv_num"],d.get("k",5))
        print(json.dumps({"chars":c}))
    elif d.get("mode")=="compare":
        s = difflib.SequenceMatcher(None,d["chars_a"],d["chars_b"]).ratio()
        print(json.dumps({"similarity":round(s,4),"similarity_pct":round(s*100,2),"fuzzy_score":round(calc_fuzzy_score(s,d.get("base",50),d.get("multiplier",2.5)),2)}))

if __name__ == "__main__":
    main()
