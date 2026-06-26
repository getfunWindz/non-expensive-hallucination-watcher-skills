import sys, json, re, os, datetime
from signal_topic import extract as topic_extract, similarity as topic_similarity

TOPIC_THRESHOLD = 0.15

def extract_claims(text):
    sents = re.split(r'[\uff0e\uff01\uff1f\n]', text)
    return [s.strip() for s in sents if len(s.strip()) >= 8 and any(kw in s for kw in ['\u662f', '\u6709', '\u53ef\u4ee5', '\u80fd\u591f', '\u5c06', '\u4f1a', '\u5df2\u7ecf'])]

def has_contradiction(new, old):
    nl, ol = new.lower(), old.lower()
    pairs = [('\u53ef\u4ee5','\u4e0d\u53ef\u4ee5'),('\u80fd\u591f','\u4e0d\u80fd\u591f'),('\u6709','\u6ca1\u6709'),('\u662f','\u4e0d\u662f'),('\u4f1a','\u4e0d\u4f1a'),('\u5df2\u7ecf','\u5c1a\u672a'),('\u652f\u6301','\u4e0d\u652f\u6301'),('\u5177\u5907','\u4e0d\u5177\u5907'),('\u5b8c\u6210','\u672a\u5b8c\u6210')]
    return any((pos in nl and neg in ol) or (neg in nl and pos in ol) for pos, neg in pairs)

def check(text, reference_entries, topic_threshold=TOPIC_THRESHOLD):
    claims = extract_claims(text)
    if not claims or not reference_entries:
        return {"score": 0, "detail": "insufficient data", "claims_count": len(claims)}
    contradictions = total_checks = 0
    for claim in claims:
        ct = topic_extract(claim, 3)
        for entry in reference_entries:
            if topic_similarity(ct, entry.get("topic", {})) < topic_threshold: continue
            for ec in entry.get("claims", []):
                total_checks += 1
                if has_contradiction(claim, ec): contradictions += 1
    return {"score": round((contradictions / max(total_checks, 1)) * 10, 2),
            "detail": f"{contradictions} in {total_checks}" if contradictions else "consistent",
            "claims_count": len(claims), "contradictions": contradictions}

def add_entry(entries, text):
    claims = extract_claims(text)
    if claims:
        entries.append({"claims": claims, "topic": topic_extract(text, 5), "timestamp": datetime.datetime.utcnow().isoformat()})
    return entries
