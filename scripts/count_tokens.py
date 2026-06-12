import tiktoken
import json
import sys

def count_tokens(text, encoding_name="cl100k_base"):
    enc = tiktoken.get_encoding(encoding_name)
    tokens = enc.encode(text)
    return len(tokens)

if __name__ == "__main__":
    try:
        data = json.loads(sys.stdin.read())
        if data.get("mode") == "full":
            full_text = data.get("text", "")
            total = count_tokens(full_text)
            print(json.dumps({"total_tokens": total, "mode": "full"}))
        else:
            input_text = data.get("input", "")
            output_text = data.get("output", "")
            result = {"input_tokens": count_tokens(input_text), "output_tokens": count_tokens(output_text), "total_tokens": 0}
            result["total_tokens"] = result["input_tokens"] + result["output_tokens"]
            print(json.dumps(result))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
