import tiktoken
import json
import sys


ENCODING = "cl100k_base"


def count_tokens(text):
    return len(tiktoken.get_encoding(ENCODING).encode(text))


def estimate_thinking(visible_text, multiplier=3.0):
    """Estimate thinking tokens based on visible output and a configurable multiplier.
    Thinking tokens are generated during model inference but are NOT visible
    to the model or measurable via tiktoken. This is an approximation.
    """
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
            print(json.dumps({
                "total_tokens": grand_total,
                "visible_tokens": visible_total,
                "estimated_thinking": estimated_thinking,
                "mode": "full",
                "thinking_multiplier": thinking_mult,
            }))

        elif data.get("mode") == "record":
            from session_store import update_last_turn

            proj = data["project_dir"]
            sid = data["session_id"]
            updates = {
                "total_tokens": data.get("total_tokens"),
                "visible_tokens": data.get("visible_tokens"),
                "estimated_thinking": data.get("estimated_thinking"),
                "thinking_multiplier": data.get("thinking_multiplier"),
            }
            updates = {k: v for k, v in updates.items() if v is not None}
            if updates:
                update_last_turn(proj, sid, updates)
            print(json.dumps({"status": "recorded", "fields": list(updates.keys())}))

        else:
            input_text = data.get("input", "")
            output_text = data.get("output", "")
            it = count_tokens(input_text)
            ot = count_tokens(output_text)
            print(json.dumps({
                "input_tokens": it,
                "output_tokens": ot,
                "total_tokens": it + ot,
            }))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
