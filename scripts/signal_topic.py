import sys, json, re
import jieba
jieba.initialize()

_STOP_WORDS = {"the", "a", "an", "is", "was", "are", "in", "of", "to", "and", "or", "for", "on", "with", "at", "by", "this", "that", "it", "not", "no", "but", "so", "if", "as", "all", "can", "will", "would", "could", "should", "may", "might", "about", "into", "through", "during", "what", "how", "why", "which", "who", "的", "了", "是", "在", "有", "和", "就", "不", "人", "都", "一", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "看", "好", "这", "那", "他", "她", "它", "们", "我", "吧", "吗", "啊", "呢", "与", "或", "及", "但", "可", "被", "把", "对", "从", "以", "而", "所", "为", "因", "由", "于", "向", "让", "比", "按", "照", "凭", "沿", "顺", "朝", "往", "跟", "同", "除", "之", "间", "其", "中", "前", "后", "内", "外", "旁", "左", "右", "每", "各", "几", "多", "少", "全", "半", "能", "够", "应", "该", "需", "必", "须", "愿", "意", "想", "希", "望", "什么", "怎么", "为什么", "如何", "哪些", "哪个", "没有", "自己", "我们", "你们", "他们", "她们", "它们", "一个"}

def extract(text, top_n=8):
    words = jieba.lcut(text)
    freq = {}
    for w in words:
        w = w.strip().lower()
        if len(w) < 2 or re.match(r'^\d+$', w) or w in _STOP_WORDS: continue
        freq[w] = freq.get(w, 0) + 1
    eng = re.findall(r'[a-zA-Z]+', text)
    for e in eng:
        el = e.lower()
        if len(el) >= 2 and el not in _STOP_WORDS:
            freq[el] = freq.get(el, 0) + 1
    sorted_w = sorted(freq.items(), key=lambda x: -x[1])
    return {k: v for k, v in sorted_w[:top_n]}

def similarity(sig_a, sig_b):
    if not sig_a or not sig_b: return 0.0
    set_a, set_b = set(sig_a.keys()), set(sig_b.keys())
    if not set_a or not set_b: return 0.0
    inter = set_a & set_b
    return len(inter) / len(set_a | set_b)
