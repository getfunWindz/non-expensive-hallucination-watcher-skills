"""
topic_embed.py — Zero-dependency topic signature + similarity for hallucination-watch.

Extracts content words as a topic signature,
computes Jaccard similarity between signatures.

Usage modes:
  extract:  {"mode":"extract","text":"法国的首都是什么？"}
            → {"signature":{"法国":1,"首都":1}}

  compare:  {"mode":"compare","sig_a":{"法国":1,"首都":1},"sig_b":{"巴黎":1,"法国":1}}
            → {"similarity":0.33,"overlap":["法国"],"threshold":0.15,"is_same_topic":true}
"""
import json
import re
import sys
from collections import Counter


STOP_WORDS = {
    # English
    "what", "is", "the", "how", "does", "do", "a", "an", "in", "of", "to",
    "and", "or", "for", "on", "with", "at", "by", "this", "that", "it",
    "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "not", "no", "but", "so", "if", "as", "all", "can", "will", "would",
    "could", "should", "may", "might", "about", "into", "through", "during",
    # Chinese multi-char
    "什么", "怎么", "为什么", "如何", "哪些", "哪个", "没有",
    "自己", "我们", "你们", "他们", "她们", "它们", "一个",
    # Chinese single-char stop words
    "的", "是", "了", "在", "有", "和", "就", "不", "人",
    "都", "一", "上", "也", "很", "到", "说", "要", "去",
    "你", "会", "着", "看", "好", "这", "那", "他", "她",
    "它", "们", "我", "吧", "吗", "啊", "呢", "噢", "哦",
    "嗯", "呗", "啦", "哟", "呀", "哇", "呵", "哈", "喂",
    "与", "或", "及", "但", "可", "被", "把", "对", "从",
    "以", "而", "所", "为", "因", "由", "于", "向", "让",
    "比", "按", "照", "凭", "沿", "顺", "朝", "往", "跟",
    "同", "除", "之", "间", "其", "中", "前", "后", "内",
    "外", "旁", "左", "右", "东", "西", "南", "北", "这",
    "那", "哪", "每", "各", "几", "多", "少", "全", "半",
    "能", "够", "可", "以", "应", "该", "需", "要", "必",
    "须", "愿", "意", "想", "要", "希", "望", "可", "能"
}


def extract_topic_sig(text):
    if not text:
        return {}
    # Match ASCII words OR individual CJK characters (each is a token)
    ascii_words = re.findall(r'[a-zA-Z]+', text)
    cjk_chars = re.findall(r'[\u4e00-\u9fff]', text)
    all_tokens = [w.lower() for w in ascii_words if len(w) > 1] + cjk_chars
    sig = Counter(t for t in all_tokens if t not in STOP_WORDS)
    return dict(sig.most_common(10))


def topic_similarity(sig_a, sig_b):
    set_a = set(sig_a.keys())
    set_b = set(sig_b.keys())
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def main():
    data = json.loads(sys.stdin.read())
    mode = data.get("mode", "extract")

    if mode == "extract":
        text = data.get("text", "")
        sig = extract_topic_sig(text)
        print(json.dumps({"signature": sig}))

    elif mode == "compare":
        sig_a = data.get("sig_a", {})
        sig_b = data.get("sig_b", {})
        threshold = data.get("threshold", 0.15)
        sim = topic_similarity(sig_a, sig_b)
        overlap = list(set(sig_a.keys()) & set(sig_b.keys()))
        print(json.dumps({
            "similarity": round(sim, 4),
            "overlap": overlap,
            "threshold": threshold,
            "is_same_topic": sim >= threshold,
        }))

    elif mode == "record":
        from session_store import update_last_turn
        update_last_turn(data["project_dir"], data["session_id"],
                         {"topic_signature": data.get("signature", {})})
        print(json.dumps({"status": "recorded"}))


if __name__ == "__main__":
    main()
