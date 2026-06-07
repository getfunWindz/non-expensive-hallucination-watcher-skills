import hashlib, json, sys

def weighted_extract(text, conv_num, profile, k=5):
    if not text: return ""
    h = hashlib.sha256(f"{text}{conv_num}".encode()).hexdigest()
    bp = profile.get("bin_probs",[0.2]*5)
    bs = max(len(text)//max(len(bp),1),1)
    chars = []
    for i in range(k):
        if i*8+16>len(h): h = hashlib.sha256(h.encode()).hexdigest()
        hv = int(h[i*8:(i+1)*8],16)
        cum, sb = 0.0, 0
        for b,p in enumerate(bp):
            cum+=p
            if (hv%1000)/1000.0<=cum: sb=b;break
        s,e = sb*bs, min((sb+1)*bs,len(text))
        if e<=s: s,e = 0, len(text)
        chars.append(text[s+(hv//1000)%max(e-s,1)])
    return "".join(chars)

def main():
    d = json.loads(sys.stdin.read())
    if d.get("mode")=="weighted_extract":
        print(json.dumps({"chars":weighted_extract(d["text"],d["conv_num"],d["profile"],d.get("k",5))}))

if __name__ == "__main__":
    main()
