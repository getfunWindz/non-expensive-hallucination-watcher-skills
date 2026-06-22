import hashlib
import json
import sys


def calc_habit_profile(bin_counts, num_bins=5):
    total = sum(bin_counts)
    if total == 0:
        uniform = round(1.0 / num_bins, 4)
        return {
            "total_samples": 0,
            "bin_probs": [uniform] * num_bins,
            "dominant_bin": None
        }

    bin_probs = [round(c / total, 4) for c in bin_counts]
    dominant_bin = bin_probs.index(max(bin_probs))

    return {
        "total_samples": total,
        "bin_probs": bin_probs,
        "dominant_bin": dominant_bin
    }


def weighted_extract_from_profile(text, conv_num, profile, k=5):
    if not text:
        return ""
    seed = f"{text}{conv_num}"
    h = hashlib.sha256(seed.encode()).hexdigest()

    bin_probs = profile.get("bin_probs", [0.2, 0.2, 0.2, 0.2, 0.2])
    num_bins = len(bin_probs)
    bin_size = max(len(text) // max(num_bins, 1), 1)

    chars = []
    for i in range(k):
        if i * 8 + 16 > len(h):
            h = hashlib.sha256(h.encode()).hexdigest()
        hash_val = int(h[i*8:(i+1)*8], 16)

        bin_rand = (hash_val % 1000) / 1000.0
        cumulative = 0.0
        selected_bin = 0
        for b, prob in enumerate(bin_probs):
            cumulative += prob
            if bin_rand <= cumulative:
                selected_bin = b
                break

        bin_start = selected_bin * bin_size
        bin_end = min((selected_bin + 1) * bin_size, len(text))
        if bin_end <= bin_start:
            bin_start = 0
            bin_end = len(text)

        pos = bin_start + (hash_val // 1000) % max(bin_end - bin_start, 1)
        pos = min(pos, len(text) - 1)
        chars.append(text[pos])

    return "".join(chars)


if __name__ == "__main__":
    try:
        data = json.loads(sys.stdin.read())
        mode = data.get("mode", "calc")

        if mode == "calc":
            bin_counts = data["bin_counts"]
            profile = calc_habit_profile(bin_counts)
            print(json.dumps(profile))

        elif mode == "weighted_extract":
            text = data["text"]
            conv_num = data["conv_num"]
            profile = data["profile"]
            k = data.get("k", 5)
            chars = weighted_extract_from_profile(text, conv_num, profile, k)
            print(json.dumps({"chars": chars}))

        elif mode == "record":
            from session_store import read_session, write_session

            proj = data["project_dir"]
            sid = data["session_id"]
            profile = data.get("profile")
            if not profile:
                print(json.dumps({"error": "missing 'profile' field"}))
            else:
                sess = read_session(proj, sid)
                sess["habit_profile"] = profile
                write_session(proj, sid, sess)
                print(json.dumps({
                    "status": "recorded",
                    "total_samples": profile.get("total_samples", 0),
                }))

    except Exception as e:
        print(json.dumps({"error": str(e)}))
