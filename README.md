<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="Hallucination Watch — 6-signal hallucination risk screening for LLM conversations">
</p>

# Hallucination Watch · 幻觉监测

A low-cost, **user-activated** hallucination risk screening skill for LLM conversations. Six behavioral proxy signals, EMA threshold adaptation, per-session isolation, MCP integration. No external APIs, no ground-truth oracles.

一款极低成本的幻觉监测 Skill：6 个行为代理信号 + EMA 阈值自适应 + 按会话隔离 + MCP 工具集成。无需第三方 API，不依赖真实标注。

## Quick Start / 快速开始

```text
User:  启动幻觉监测
Agent: → calls hw_init
       → .hw_active created, AGENTS.md monitoring rule injected
       → every subsequent reply: calls hw_check(text=回复全文, prev_text=上一轮)
       → high risk: risk card (MARK / VERIFY)
       → hard trigger: 2+ red-flag phrases → MARK immediately

User:  hw_status     → session stats (checks / alerts / habit profile)
User:  hw_reset      → clears session, marker, and AGENTS.md rule
```

## Why It Is Different / 与常规监测的区别

| Signal | What it checks | 中文说明 |
|:---|:---|:---|
| **Keyword density** | Absolute statements + red-flag phrases (3× weight) | 关键词密度：绝对化表述 + 红旗词（3 倍权重） |
| **Self-consistency** | Jaccard similarity across turns | 自洽性：跨轮 Jaccard 相似度 |
| **Fuzzy match** | k-char fingerprint overlap | 模糊匹配：k 字符指纹哈希，仅部分相似（0.3–0.7）计分 |
| **Material consistency** | Topic-gated contradiction detection (jieba) | 素材一致性：jieba 话题门控 + 矛盾检测 |
| **Redundancy** | Cumulative text volume (capped) | 冗余度：累计文本量线性增长（有上限） |
| **Habit profile** | Character-position 5-bin distribution | 习惯画像：字符位置 5-bin 分布 + 异常度 |

**Hard trigger 硬触发**：2 个及以上红旗词（毫无疑问 / 百分百 / 百分之百 / 绝对保证 / 万无一失 …）直接判定 **MARK**——不经过密度归一化，长文本不会稀释信号。

**实测区分度**：高危文本 100% MARK vs 正常文本 2% SAFE（修复前为 60% vs 51%）。

## How It Works / 工作原理

```
risk_raw = keyword × multiplier + consistency + fuzzy + material + redundancy + habit
risk_pct = risk_raw / threshold × 100        (threshold: per-session EMA 自适应)

Zone:  safe (<100%)  → silent
       mark (100–250%) → risk card
       verify (≥250%) → risk card
```

- **EMA threshold adaptation**: threshold self-tunes per session based on trigger rate (written to `session.json`, never pollutes global params).
- **Per-session isolation**: sessions stored under `sessions/{session_id}/`, idempotent init reuses the active session across restarts.
- **Crash-safe persistence**: atomic writes (`tmp` + `os.replace`).
- **Bounded storage**: turn text truncated at 500 chars with full-length counting via `cumulative_text_len`; reference entries capped at 50 with dedup.

## Install / 安装

### Via MCP (any MCP-capable agent)

```json
{
  "mcpServers": {
    "hallucination-watch": {
      "command": "python",
      "args": ["/path/to/hallucination-watch/scripts/hallucination_watch_mcp.py"]
    }
  }
}
```

Standard MCP stdio protocol (FastMCP) — works with any MCP-capable agent (pi, opencode, Claude Code, …).

### Via CLI (standalone)

```bash
python scripts/monitor.py init
python scripts/monitor.py check --file=response.json
python scripts/monitor.py status
python scripts/monitor.py reset
```

### Requirements

`python ≥3.9` · `mcp` · `pydantic` · `jieba`

## Architecture / 架构

```
hallucination-watch/
├── SKILL.md                        ← Skill descriptor (Agent Skills spec)
├── README.md
├── assets/readme/                  ← README visuals (SVG)
├── params/
│   └── default.json                ← 19 configurable parameters
├── scripts/
│   ├── hallucination_watch_mcp.py  ← MCP server (4 tools, stdio)
│   ├── monitor.py                  ← CLI entry (standalone)
│   ├── check_compliance.py         ← Compliance verifier (window-parameterized)
│   ├── signal_keyword.py           ← Signal 1: keyword density + red flags
│   ├── signal_consistency.py       ← Signal 2: Jaccard consistency
│   ├── signal_fuzzy.py             ← Signal 3: fingerprint match (partial-sim only)
│   ├── signal_material.py          ← Signal 4: topic-gated contradiction
│   ├── signal_redundancy.py        ← Signal 5: cumulative redundancy (capped)
│   ├── signal_habit.py             ← Signal 6: position distribution
│   ├── signal_adapt.py             ← EMA threshold adaptation (per-session)
│   ├── signal_topic.py             ← jieba topic embedding
│   └── signal_correction.py        ← Optional auto-correction (default off)
├── tests/
│   └── test_hallucination_watch.py ← 55 unit tests
└── sessions/                       ← Per-session data (auto-created, gitignored)
```

## Tests / 测试

```bash
python -m unittest tests.test_hallucination_watch -v
# 55 tests · signals / lifecycle / storage bounds / EMA / review regressions
```

## Parameter Reference / 参数参考

| Parameter | Default | Description |
|:---|:---:|:---|
| threshold | 22.0 | Initial risk threshold (per-session EMA adjusts it) |
| density_multiplier | 10 | Keyword density multiplier |
| red_flag_keywords | 10 items | Hard-trigger phrases (≥2 → MARK) |
| k_chars | 7 | Fuzzy fingerprint length |
| num_bins | 5 | Habit profile bins |
| redundancy_max_score | 40 | Redundancy score cap |
| max_baseline_n | 10 | Baseline → active phase transition |
| adaptation_interval | 10 | EMA re-calibration interval (turns) |
| target_trigger_rate | 0.10 | EMA target trigger rate |
| topic_similarity_threshold | 0.15 | Topic gate for material checks |

Full list in `params/default.json`.

## License / 许可证

MIT
