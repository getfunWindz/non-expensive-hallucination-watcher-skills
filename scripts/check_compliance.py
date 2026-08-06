#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
check_compliance.py — 履约验证脚本。

被插件在 session.idle 时调用。
检查逻辑：
  1. 项目根目录是否存在 .hw_active 标记
  2. 若存在，读取最新（.hw_active 指向）的 hallucination-watch 会话
  3. 检查 turns.json 中最新记录的时间戳是否在窗口内（默认 60 秒，参数化）
  4. 输出 JSON: {"compliant": true/false, "last_check": "..."}

用法：python check_compliance.py [project_root]
"""
import sys, json, os
from datetime import datetime, timezone

# sessions 实际存储在 skill 目录下（与 MCP 脚本一致），而非项目根目录。
_SESSIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sessions"
)
# 默认履约窗口（秒）：从 30 放宽到 60，避免插件在 session.idle 时误报 stale。
DEFAULT_WINDOW_SECONDS = 60


def check_with_dirs(project_root, sessions_dir, window_seconds=DEFAULT_WINDOW_SECONDS):
    """检查指定项目与 sessions 目录的履约情况（sessions_dir 可注入，便于测试）。

    Args:
        project_root: 项目根目录（.hw_active 所在）
        sessions_dir: 会话存储目录（默认为 skill 目录下的 sessions）
        window_seconds: 履约时间窗口（秒），默认 60
    """
    hw_active = os.path.join(project_root, ".hw_active")
    # 1. Check marker exists
    if not os.path.exists(hw_active):
        return {"compliant": True, "reason": "not_active"}

    # 2. Read session ID from .hw_active (not from directory scan)
    with open(hw_active, encoding="utf-8") as f:
        sid = f.read().strip()

    # 2b. If the session dir doesn't exist (data was deleted), fall back to scanning
    latest_sid = sid
    sd = os.path.join(sessions_dir, sid)
    if not os.path.exists(sd):
        if not os.path.exists(sessions_dir):
            return {"compliant": False, "reason": "no_sessions_dir"}
        all_s = sorted(os.listdir(sessions_dir), reverse=True)
        if not all_s:
            return {"compliant": False, "reason": "no_sessions"}
        latest_sid = all_s[0]
    turns_path = os.path.join(sessions_dir, latest_sid, "turns.json")
    if not os.path.exists(turns_path):
        return {"compliant": False, "reason": "no_turns_file"}

    with open(turns_path, encoding="utf-8") as f:
        data = json.load(f)

    turns = data.get("turns", [])
    if not turns:
        return {"compliant": False, "reason": "no_checks_yet", "turn_count": 0}

    # 3. Check latest turn timestamp
    latest = turns[-1]
    ts_str = latest.get("timestamp", "")
    if not ts_str:
        return {"compliant": False, "reason": "no_timestamp"}

    try:
        last_time = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = (now - last_time).total_seconds()
    except Exception:
        return {"compliant": False, "reason": "bad_timestamp"}

    if delta < window_seconds:
        return {
            "compliant": True,
            "reason": "recently_checked",
            "last_turn": latest.get("turn"),
            "seconds_ago": round(delta, 1),
            "zone": latest.get("zone"),
            "risk_pct": latest.get("risk_pct")
        }
    else:
        return {
            "compliant": False,
            "reason": "stale_check",
            "last_turn": latest.get("turn"),
            "seconds_ago": round(delta, 1),
            "window_seconds": window_seconds
        }


def check(project_root):
    """默认实现：sessions 位于 skill 目录下，窗口 60 秒。"""
    return check_with_dirs(project_root, _SESSIONS_DIR)


if __name__ == "__main__":
    project_root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = check(project_root)
    print(json.dumps(result, ensure_ascii=False))
