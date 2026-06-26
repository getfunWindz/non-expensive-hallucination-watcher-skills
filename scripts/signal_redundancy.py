import sys, json

def calc(total_text_len, params):
    tpi = params.get("redundancy_tokens_per_increment", 1000)
    inc = params.get("redundancy_increment", 5)
    return round((total_text_len / tpi) * inc, 2)
