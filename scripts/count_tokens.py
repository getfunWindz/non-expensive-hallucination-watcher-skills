import tiktoken, json, sys

def count_tokens(text, enc="cl100k_base"):
    return len(tiktoken.get_encoding(enc).encode(text))

if __name__ == "__main__":
    try:
        d = json.loads(sys.stdin.read())
        r = {"input_tokens":count_tokens(d.get("input","")),"output_tokens":count_tokens(d.get("output","")),"total_tokens":0}
        r["total_tokens"] = r["input_tokens"] + r["output_tokens"]
        print(json.dumps(r))
    except Exception as e:
        print(json.dumps({"error":str(e)}))
