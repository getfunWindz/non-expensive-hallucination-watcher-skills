# Hallucination Watch · 幻觉监测

> A low-cost, user-activated hallucination risk screening skill for LLM conversations.
> Uses 6 behavioral proxy signals with EMA threshold adaptation. Per-session isolation.
>
> 一款极低成本的幻觉检测与纠错 Skill，基于 6 个行为代理信号 + EMA 阈值自适应。
> 按会话隔离，支持 MCP 工具集成。

---

## Overview / 概述

**English**

This skill monitors LLM responses for hallucination risk using behavioral proxy signals — no expensive external API calls, no ground-truth oracles. When the user activates monitoring, every subsequent response is checked across 6 dimensions. Results are persisted per-session in JSON files for audit and analysis.

**中文**

本 Skill 通过行为代理信号对 LLM 回复进行幻觉风险监测——无需昂贵的第三方 API，不依赖真实标注。用户激活监测后，每次回复都经过 6 个维度的检查。结果按会话持久化为 JSON 文件，支持审计和分析。

---

## Features / 特性

| English | Chinese |
|:---|:---|
| **6 signals**: keyword density, self-consistency, fuzzy match, material consistency, redundancy, habit profile | **6 信号监测**：关键词密度、自洽性、模糊匹配、素材一致性、冗余度、习惯画像 |
| **Powerful Chinese support**: jieba word segmentation + stop word filtering + character bigram topic extraction | **中文深度优化**：jieba 分词 + 停用词过滤 + 字符 bigram 话题提取 |
| **EMA threshold adaptation**: self-tuning threshold based on trigger rate | **EMA 阈值自适应**：根据触发率自动调优阈值 |
| **MCP integration**: 4 tools (init/check/status/reset) for opencode | **MCP 集成**：4 个工具（init/check/status/reset） |
| **Idempotent init**: restart-safe, won't create duplicate sessions | **幂等初始化**：重启安全，不会重复创建会话 |
| **AGENTS.md management**: auto-writes monitoring rules on init | **AGENTS.md 自动管理**：初始化时写入监测规则 |
| **Atomic writes**: crash-safe data persistence | **原子写入**：崩溃安全的数据持久化 |
| **File structure**: human-readable JSON data files | **文件结构**：人类可读的 JSON 数据文件 |

---

## Quick Start / 快速开始

### 1. Install / 安装

Place the skill in your opencode skills directory:

```bash
cp -r hallucination-watch ~/.config/opencode/skills/
```

### 2. Register MCP / 注册 MCP 服务

Add to `~/.config/opencode/opencode.json`:

```json
{
  "mcp": {
    "hallucination-watch": {
      "type": "local",
      "command": ["python", "~/.config/opencode/skills/hallucination-watch/scripts/hallucination_watch_mcp.py"],
      "enabled": true
    }
  }
}
```

### 3. Use / 使用

```text
User:  启动幻觉监测
Agent: → calls hw_init → .hw_active created + AGENTS.md rule injected
       → every response: calls hw_check(text=...)
       → if triggered: shows risk card

User:  hw_status
Agent: → shows session stats

User:  hw_reset
Agent: → clears all data + removes AGENTS.md rule
```

---

## Architecture / 架构

```
hallucination-watch/
├── SKILL.md                        ← Skill descriptor
├── README.md                       ← This file
├── params/
│   └── default.json                ← 18 configurable parameters
├── scripts/
│   ├── hallucination_watch_mcp.py  ← MCP server (4 tools)
│   ├── monitor.py                  ← CLI entry (standalone use)
│   ├── check_compliance.py         ← Plugin compliance verifier
│   ├── signal_keyword.py           ← Signal 1: keyword density
│   ├── signal_consistency.py       ← Signal 2: Jaccard consistency
│   ├── signal_fuzzy.py             ← Signal 3: fingerprint hash
│   ├── signal_material.py          ← Signal 4: topic-gated material check
│   ├── signal_redundancy.py        ← Signal 5: cumulative redundancy
│   ├── signal_habit.py             ← Signal 6: position distribution
│   ├── signal_adapt.py             ← EMA threshold adaptation
│   ├── signal_topic.py             ← Topic embedding (jieba + stop words)
│   └── signal_correction.py        ← Optional auto-correction (disabled)
└── sessions/                       ← Per-session data (auto-created)
    └── {session_id}/
        ├── session.json
        ├── turns.json
        └── reference.json
```

---

## Decision Formula / 决策公式

```
risk_raw = keyword_density × 10 + consistency + fuzzy + material + redundancy + habit_anomaly
risk_pct = risk_raw / threshold × 100

Zone:
  safe:   risk_pct < 100   → silent
  mark:   100 ≤ risk_pct < 250 → card display
  verify: risk_pct ≥ 250   → card display
```

---

## Parameter Reference / 参数参考

| Parameter | Default | Description |
|:---|:---:|:---|
| threshold | 22 | Risk threshold |
| density_multiplier | 10 | Keyword score multiplier |
| k_chars | 7 | Fuzzy match fingerprint length |
| num_bins | 5 | Habit profile bin count |
| redundancy_tokens_per_increment | 1000 | Redundacy scaling |
| redundancy_increment | 5 | Redundancy per increment |
| min_baseline_n | 3 | Min baseline turns |
| max_baseline_n | 10 | Max baseline / start active |
| adaptation_interval | 10 | EMA re-calibration frequency |
| correction_enabled | false | Auto-correction toggle |
| target_trigger_rate | 0.10 | EMA target trigger rate |
| ema_alpha | 0.3 | EMA smoothing factor |
| threshold_increase_factor | 1.10 | Threshold increase multiplier |
| threshold_decrease_factor | 0.90 | Threshold decrease multiplier |
| topic_similarity_threshold | 0.15 | Topic gate threshold |

---

## Comparison with v1 / 与 v1 对比

| Aspect | v1 (original) | v2 (current) |
|:---|:---|:---|
| Parameters | 35 | 18 |
| Signal modules | 8 | 9 (added correction) |
| Chinese path support | ❌ Broken | ✅ Works |
| Idempotent init | ❌ | ✅ |
| MCP tools | ❌ | ✅ (4 tools) |
| AGENTS.md management | ❌ | ✅ |
| Atomic writes | ❌ | ✅ |
| Full-text storage | ❌ (80 char preview) | ✅ (full text) |
| Stop word filtering | ❌ | ✅ |
| Threshold adaptation | Complex script | Lightweight EMA |

---

## License / 许可证

MIT

---

## Links / 链接

- GitHub: https://github.com/getfunWindz/non-expensive-hallucination-watcher-skills
- MCP Server: https://github.com/getfunWindz/hallucination-watch-mcp
