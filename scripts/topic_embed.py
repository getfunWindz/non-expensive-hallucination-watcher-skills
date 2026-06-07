import json, re, sys
from collections import Counter

STOP = {"what","is","the","how","does","do","a","an","in","of","to","and","or","for","on","with","at","by","this","that","it","are","was","were","be","been","being","have","has","had","not","no","but","so","if","as","all","can","will","would","could","should","may","might","about","into","through","during","什么","怎么","为什么","如何","哪些","哪个","没有","自己","我们","你们","他们","她们","它们","一个","的","是","了","在","有","和","就","不","人","都","一","上","也","很","到","说","要","去","你","会","着","看","好","这","那","他","她","它","们","我","吧","吗","啊","呢","噢","哦","嗯","呗","啦","哟","呀","哇","呵","哈","喂","与","或","及","但","可","被","把","对","从","以","而","所","为","因","由","于","向","让","比","按","照","凭","沿","顺","朝","往","跟","同","除","之","间","其","中","前","后","内","外","旁","左","右","东","西","南","北","这","那","哪","每","各","几","多","少","全","半","能","够","可","以","应","该","需","要","必","须","愿","意","想","要","希","望","可","能"}

def extract(text):
    if not text: return {}
    aw = re.findall(r'[a-zA-Z]+',text)
    cjk = re.findall(r'[\u4e00-\u9fff]',text)
    return dict(Counter(t.lower() for t in aw if len(t)>1)+Counter(c for c in cjk if c not in STOP).most_common(10))

def similarity(a,b):
    sa,sb = set(a.keys()), set(b.keys())
    if not sa or not sb: return 0.0
    return len(sa&sb)/len(sa|sb)

def main():
    d = json.loads(sys.stdin.read())
    if d.get("mode")=="extract": print(json.dumps({"signature":extract(d.get("text",""))}))
    elif d.get("mode")=="compare":
        s = similarity(d["sig_a"],d["sig_b"])
        print(json.dumps({"similarity":round(s,4),"overlap":list(set(d["sig_a"].keys())&set(d["sig_b"].keys())),"threshold":d.get("threshold",0.15),"is_same_topic":s>=d.get("threshold",0.15)}))

if __name__ == "__main__":
    main()
