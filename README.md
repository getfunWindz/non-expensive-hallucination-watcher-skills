# Hallucination Watch · 幻觉监测

**Language**: [中文](#chinese) | [English](#english)

---

<a name="chinese"></a>

## 中文介绍

### 概述

Hallucination Watch 是一个**用户主动激活的幻觉风险监测系统**。它通过行为代理信号（而非事实核查）来估算 LLM 回答中可能存在的幻觉风险。

### 工作原理

系统追踪三个代理信号：

| 信号 | 含义 | 来源 |
|------|------|------|
| **关键词密度** | 主观/绝对化用词在回答中的密度 | 关键词匹配 + token 归一化 |
| **模糊匹配分数** | 跨轮次回答的字符级一致性 | `fuzzy_match.py` (difflib) |
| **冗余分数** | 累积对话长度带来的风险递增 | `count_tokens.py` (tiktoken) |

三个信号加权求和 → `formula_raw` → 与动态阈值比较 → 三区决策（Safe/Mark/Verify）。

### 两阶段设计

| 阶段 | 行为 |
|------|------|
| **Baseline** (前 N 轮) | 仅记录指标，构建习惯画像，不触发任何操作 |
| **Active** (N+1 轮起) | 全面检测，达到阈值时触发纠错 |

两个阶段之间的阈值校准是数据驱动的——当 baseline 指标的变异系数稳定在 0.3 以下时自动切入 Active。

### 文件结构

```
{project_root}/hallucination-watch/
├── params.json                    # 自适应阈值（学习层，动态覆盖）
└── sessions/{session_id}/
    ├── session.json               # 会话元数据 + 累计计数器
    ├── turns.json                 # 每轮对话的完整指标数组
    └── reference.json             # 参考资料条目（一致性检查）
```

### 关键改进

本次重构（v2）彻底解决了旧版本的数据丢失问题：

- **每个脚本独立持久化**：每个 pipeline 脚本都有 `record` 模式，计算完直接写入磁盘
- **集中式数据访问层**：`session_store.py` 统一管理所有 JSON 文件的路径和读写逻辑
- **完整 schema**：`turns.json` 记录每轮对话的全部指标，`session.json` 维护累计状态
- **废弃 permanent.json**：其数据完全并入 `turns.json`

---

## 使用方式

用户说出触发短语之一即可激活：

- `启动幻觉监测` / `开始监测` / `幻觉检测`
- `start monitoring` / `hallucination check`

停止监测：`停止监测` / `stop monitoring`

---

<a name="english"></a>

## English

### Overview

Hallucination Watch is a **user-activated hallucination risk monitor** that estimates hallucination probability in LLM responses using behavioural proxy signals — without requiring a ground-truth oracle or external verification on every turn.

### How It Works

Three proxy signals are tracked per conversation turn:

| Signal | Meaning | Source |
|--------|---------|--------|
| **Keyword density** | Normalised count of subjective/absolute phrasing | Keyword matching + token normalisation |
| **Fuzzy match score** | Cross-turn character-level consistency | `fuzzy_match.py` (difflib) |
| **Redundancy score** | Cumulative conversation-length risk | `count_tokens.py` (tiktoken) |

These are summed → `formula_raw` → compared against a dynamic threshold → three-zone decision (Safe / Mark / Verify).

### Two-Phase Design

| Phase | Behaviour |
|-------|-----------|
| **Baseline** (first N turns) | Record-only. Builds habit profile, collects formula_raw for calibration. No alerts. |
| **Active** (turn N+1 onward) | Full detection. Corrections trigger when threshold is crossed. |

The Baseline → Active transition is data-driven: it calibrates automatically when the coefficient of variation of baseline metrics drops below 0.3 (configurable).

### File Structure

```
{project_root}/hallucination-watch/
├── params.json                    # Self-adapted threshold (learning layer)
└── sessions/{session_id}/
    ├── session.json               # Session metadata + cumulative counters
    ├── turns.json                 # Per-turn metric array
    └── reference.json             # Reference material entries
```

### Key Improvements in v2

This refactoring (v2) eliminates the critical data-loss problem of the previous version:

- **Each script self-persists**: Every pipeline script has a `record` mode that writes directly to disk
- **Unified data access layer**: `session_store.py` centralises all JSON file paths and read/write logic
- **Complete schema**: `turns.json` captures every metric per turn; `session.json` maintains cumulative state
- **`permanent.json` removed**: Its data is fully merged into `turns.json`

### Usage

Say one of the trigger phrases to start:

- `start monitoring` / `hallucination check` / `activate shelter`
- `启动幻觉监测` / `开始监测` / `幻觉检测`

Stop with: `stop monitoring` / `停止监测`

### Scripts Reference

| Script | Function |
|--------|----------|
| `session_store.py` | Unified data access layer (read/write turns.json, session.json) |
| `init_skill.py` | Initialise session directory and data files |
| `topic_embed.py` | Topic signature extraction + Jaccard similarity |
| `fuzzy_match.py` | Hash-based char extraction + difflib fuzzy comparison |
| `count_tokens.py` | Token counting via tiktoken (cl100k_base) |
| `complexity_estimator.py` | Question complexity → thinking token estimate |
| `calc_habit.py` | Habit profile (5-bin probability distribution) |
| `reference_material.py` | Reference material store + consistency check |
| `correction.py` | Claim prioritisation + A/B correction method selection |
| `calibrate_threshold.py` | Baseline calibration (variance-based dynamic N) |
| `adapt_threshold.py` | EMA self-adaptation of threshold + redundancy scaling |

---

## License

MIT
