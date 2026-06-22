"""
correction.py — Self-correction support for hallucination-watch v3.0.

Provides:
  - Claim prioritization (sort by risk signals)
  - Direction B vs Direction A selection mechanism
  - Result formatting
"""
import json
import sys


def score_claim(claim_text, subjective_positions, claim_position, fuzzy_score):
    """
    Score a claim's priority for verification.
    Higher score = verify first.
    """
    score = 0

    # Factor 1: Proximity to subjective keywords
    if subjective_positions and claim_position is not None:
        min_dist = min(abs(claim_position - sp) for sp in subjective_positions)
        if min_dist < 50:
            score += 30
        elif min_dist < 100:
            score += 15
        elif min_dist < 200:
            score += 5

    # Factor 2: Fuzzy match score from cross-session comparison
    score += fuzzy_score / 10

    # Factor 3: Prefer shorter claims (easier/cheaper to verify)
    text_len = len(claim_text) if claim_text else 0
    if text_len < 30:
        score += 10
    elif text_len < 60:
        score += 5

    return score


def select_claims(claims, max_claims=3):
    """Score and select top claims for verification."""
    scored = []
    for claim in claims:
        s = score_claim(
            claim.get("text", ""),
            claim.get("subjective_positions", []),
            claim.get("position"),
            claim.get("fuzzy_score", 0),
        )
        scored.append({
            "text": claim["text"],
            "score": round(s, 2),
            "position": claim.get("position", 0),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    selected = scored[:max_claims]
    selected.sort(key=lambda x: x["position"])
    return selected


def decide_method(history, params):
    """
    Decide which correction method(s) to use.

    Returns:
      { "use_b": bool, "use_a": bool, "reason": str }
    """
    first_trigger = not history.get("correction_method")
    b_accuracy = history.get("b_path_accuracy", 0.5)
    b_min = params.get("b_path_min_accuracy", 0.8)
    token_pct = params.get("token_usage_pct", 0)

    if first_trigger:
        return {"use_b": True, "use_a": True, "reason": "first_trigger"}

    if b_accuracy < b_min:
        return {"use_b": False, "use_a": True, "reason": "b_path_unreliable"}

    if token_pct < 80:
        return {"use_b": True, "use_a": True, "reason": "sufficient_budget"}

    return {"use_b": True, "use_a": False, "reason": "budget_saving"}


def format_result(corrections, claim_count, verified_count):
    """Format correction layer output."""
    correction_count = len(corrections)
    return {
        "corrections": corrections,
        "correction_count": correction_count,
        "claim_count": claim_count,
        "verified_count": verified_count,
        "all_correct": correction_count == 0,
        "correction_rate": correction_count / max(claim_count, 1),
    }


def main():
    data = json.loads(sys.stdin.read())
    mode = data.get("mode", "prioritize")

    if mode == "prioritize":
        claims = data.get("claims", [])
        max_claims = data.get("max_claims", 3)
        selected = select_claims(claims, max_claims)
        print(json.dumps({"selected": selected}, ensure_ascii=False))

    elif mode == "decide":
        history = data.get("history", {})
        params = data.get("params", {})
        decision = decide_method(history, params)
        print(json.dumps(decision))

    elif mode == "format":
        result = format_result(
            data.get("corrections", []),
            data.get("claim_count", 0),
            data.get("verified_count", 0),
        )
        print(json.dumps(result, ensure_ascii=False))

    elif mode == "record":
        from session_store import update_last_turn
        corr = {
            "method": data.get("method"),
            "correction_applied": data.get("correction_applied", False),
            "claims_extracted": data.get("claims_extracted", 0),
            "claims_verified": data.get("claims_verified", 0),
            "claims_wrong": data.get("claims_wrong", 0),
            "correction_rate": data.get("correction_rate", 0.0),
            "user_contested": data.get("user_contested", False),
        }
        update_last_turn(data["project_dir"], data["session_id"],
                         {"correction": corr})
        print(json.dumps({"status": "recorded"}))


if __name__ == "__main__":
    main()
