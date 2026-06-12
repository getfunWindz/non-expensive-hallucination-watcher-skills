import tiktoken
import json
import sys

ENCODING = "cl100k_base"

def count_tokens(text):
    return len(tiktoken.get_encoding(ENCODING).encode(text))

def estimate_thinking(visible_text, multiplier=3.0):
    visible_tokens = count_tokens(visible_text)
    return int(visible_tokens * multiplier)

if __name__ == "__main__":
    try:
        data = json.loads(sys.stdin.read())
        if data.get("mode") == "full":
            full_text = data.get("text", "")
            visible_total = count_tokens(full_text)
            thinking_mult = data.get("thinking_multiplier", 3.0)
            thinking_est = data.get("thinking_estimate", None)
            if thinking_est is not None:
                estimated_thinking = int(thinking_est)
            elif data.get("thinking_enabled", True):
                estimated_thinking = int(visible_total * thinking_mult)
            else:
                estimated_thinking = 0
            grand_total = visible_total + estimated_thinking
            print(json.dumps({"total_tokens": grand_total, "visible_tokens": visible_total, "estimated_thinking": estimated_thinking, "mode": "full"}))
        else:
            input_text = data.get("input", "")
            output_text = data.get("output", "")
            it = count_tokens(input_text)
            ot = count_tokens(output_text)
            print(json.dumps({"input_tokens": it, "output_tokens": ot, "total_tokens": it + ot}))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
