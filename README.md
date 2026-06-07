# Hallucination Watch / 幻觉监测

[English](#english) | [中文](#中文)

---

## English

### Overview

**Hallucination Watch** is an opencode skill that screens LLM conversations for hallucination risk at low cost. It uses behavioral proxy signals (subjective language, cross-session consistency) to estimate risk. It stays silent during safe conversations and only alerts when risk is detected.

### How It Works

| Signal | Description |
|--------|-------------|
| **Subjective Keywords** | Counts assertive words ("certainly", "definitely", "absolutely") that correlate with overconfidence |
| **Cross-Session Fuzzy Match** | Compares random character samples across conversations; low similarity may indicate inconsistency |
| **Token Redundancy** | Tracks total token usage; very long conversations with high redundancy get additional scrutiny |

These three signals feed into a decision formula:

```
trigger_score = subjective_count + fuzzy_match_score + redundancy_score
if trigger_score >= threshold → Web Fetch verification
```

The algorithm operates in two phases:

1. **Baseline (first N conversations)**: Records data silently, builds response habit profile
2. **Active (N+1 onwards)**: Full detection with habit-profile-weighted sampling

### Self-Adaptation Layer

Every N conversations (default: 10), an adaptation script scans the historical trigger rate and automatically adjusts the threshold:

- **Trigger rate too high** (>12%): Threshold raised by 10% (makes Web Fetch harder to trigger)
- **Trigger rate too low** (<8%): Threshold lowered by 10% (makes Web Fetch easier to trigger)
- **EMA safety net**: Prevents threshold from drifting to absurd values by pulling it toward recent trend

### Self-Correction Layer

When the decision formula triggers, a two-direction verification workflow runs:

| Direction | Cost | Method |
|-----------|------|--------|
| **B — Internal Self-Consistency** | ~200-500 thinking tokens, zero API | Re-derives answer via independent reasoning path; compares both paths internally |
| **A — Claim Verification** | 1-3 Web Fetch calls | Extracts factual claims, prioritizes by risk signals, verifies top N via Web Fetch |

The selection mechanism dynamically chooses which direction(s) to use:
- **First trigger**: Run both A+B to establish baseline
- **B-path accuracy < 80%**: Use A only (B unreliable)
- **Token budget < 80%**: Use A+B (sufficient budget)
- **Token budget >= 80%**: Use B only; escalate to A if divergence detected

Direction B runs entirely in internal thinking — invisible to the user, documented here for transparency.

### Installation

1. Ensure `tiktoken` is installed:
   ```bash
   pip install tiktoken
   ```

2. Place the skill in your opencode skills directory:
   ```
   ~/.config/opencode/skills/hallucination-watch/
   ```

3. The skill activates automatically on every conversation.

### Data Files

When active, the skill creates a `hallucination-watch/` directory in your project root:

| File | Purpose |
|------|---------|
| `session.json` | Current and previous conversation records (refreshed each turn) |
| `permanent.json` | All historical comparison results with timestamps |
| `params.json` | (Auto-generated) Overridden threshold from adaptation layer |

### Output

Every response ends with a metrics card:

```
─── hallucination-watch ──────────────────────────────────
 Input: 847 | Output: 1,203 | Total: 2,050
 Subjective: 4 | FuzzyDiff: 76% | Redundancy: 0
 Risk: 0.01% | Threshold: 100% | Status: Safe
──────────────────────────────────
```

When the correction layer identifies an error, a correction block follows:

```
─── hallucination-watch ──────────────────────────────────
 ... Metrics ...
──────────────────────────────────

[自我纠错 / Self-Correction]
 发现 1/3 条声明需修正:

 • 原: "法国的首都是里昂"
   正: "法国的首都是巴黎"

 修正率: 33% | 方法: A+B | B路径: 一致
──────────────────────────────────
```

### Architecture

```
hallucination-watch/
├── SKILL.md                    # Model instructions
├── README.md                   # This file
├── scripts/
│   ├── calibrate_threshold.py  # Baseline calibration (dynamic N)
│   ├── adapt_threshold.py      # EMA self-adaptation
│   ├── correction.py           # Claim prioritization + A/B selection
│   ├── count_tokens.py         # Token counting (tiktoken)
│   ├── fuzzy_match.py          # Hash extraction + fuzzy comparison
│   ├── calc_habit.py           # Habit profile computation
│   ├── topic_embed.py          # Topic signature + Jaccard similarity
│   └── reference_material.py   # Material store + consistency check
├── tools/
│   ├── compare_models.py       # Multi-model offline comparison
│   └── e2e_test.py             # End-to-end pipeline test
├── references/
│   └── algorithm-spec.md       # Full technical specification
└── params/
    └── default.json            # Default parameters
```

### Roadmap

- **v1.0**: Core algorithm — subjective counting, fuzzy matching, token tracking, decision formula ✅
- **v2.0**: Self-adaptation layer — dynamic threshold adjustment via EMA and trigger rate feedback ✅
- **v3.0**: Self-correction layer — two-direction verification (B: internal consistency, A: claim Web Fetch) ✅

### Limitations

| # | Limitation |
|---|-----------|
| 1 | **Score is relative, not absolute.** It compares against this model's own baseline, not an absolute hallucination probability. |
| 2 | **Subjective words ≠ hallucinations.** This signal is directional, not definitive. |
| 3 | **Cross-session comparison is topic-sensitive.** Topic tracking helps but does not eliminate noise from topic drift. |
| 4 | **Direction B can share blind spots.** Two reasoning paths can both use the same incorrect knowledge. |
| 5 | **No benchmark data available.** Accuracy has not been measured against a labeled dataset. |
| 6 | **Designed as a pre-filter.** Not a replacement for thorough fact-checking on critical content. |
| 7 | **Density normalization assumes linearity.** Very short responses (<20 tokens) may have inflated density. |
| 8 | **Reference material is topic-gated.** Only activates after 3 consecutive same-topic conversations. |
| 9 | **Material stores model statements, not verified facts.** Material checks for self-contradiction, not factual accuracy. |

### License

MIT

---

## 中文

### 概述

**Hallucination Watch** 是一个 opencode 技能，以低成本筛查 LLM 对话中的幻觉风险。它使用行为代理信号（主观语言、跨会话一致性）估算风险。安全对话保持静默，仅在有风险时提醒用户。

### 工作原理

| 信号 | 说明 |
|------|------|
| **主观关键词** | 统计"一定"、"绝对"等主观断言词汇，这些词与过度自信相关 |
| **跨会话模糊比对** | 跨对话随机截取回复字符片段进行比对；相似度低可能表示不一致 |
| **Token 冗余** | 追踪总 Token 用量；长对话且高冗余时增加关注度 |

三个信号输入决策公式：

```
触发得分 = 主观计数 + 模糊比对得分 + 冗余得分
如果触发得分 >= 阈值 → 启动 Web Fetch 验证
```

算法分两个阶段：

1. **基线阶段（前 N 次对话）**：静默记录数据，建立回复习惯削面
2. **活跃阶段（第 N+1 次起）**：完整检测，结合习惯削面加权采样

### 自主学习层

每 N 次对话（默认 10 次），迭代脚本自动扫描历史触发率并调整阈值：

- **触发率过高**（>12%）：阈值上调 10%（更不容易触发 Web Fetch）
- **触发率过低**（<8%）：阈值下调 10%（更容易触发 Web Fetch）
- **EMA 安全保底**：防止阈值漂移到不合理数值

### 自我纠错层

触发公式生效时，执行双方向验证工作流：

| 方向 | 成本 | 方式 |
|------|------|------|
| **B — 内部自治性** | ~200-500 thinking tokens，零外部调用 | 用独立推理路径重新推导答案，内部比对两条路径 |
| **A — 声明验证** | 1-3 次 Web Fetch | 提取事实性声明，按风险信号排序，验证 Top N |

选择机制动态决定使用的方向：
- **首次触发**：同时使用 A+B 建立基线
- **B 路径准确率 < 80%**：只用 A（B 不可靠）
- **Token 预算 < 80%**：使用 A+B（预算充足）
- **Token 预算 >= 80%**：只用 B；检测到不一致时降级到 A

方向 B 完全在内部 thinking 中运行——对用户不可见，此处透明公开。

### 安装

1. 确保已安装 `tiktoken`：
   ```bash
   pip install tiktoken
   ```

2. 将 skill 放入 opencode skills 目录：
   ```
   ~/.config/opencode/skills/hallucination-watch/
   ```

3. 每次对话自动激活。

### 数据文件

启用后，在项目根目录下创建 `hallucination-watch/` 目录：

| 文件 | 用途 |
|------|------|
| `session.json` | 当前和上一次对话记录（每次刷新） |
| `permanent.json` | 全部历史比对结果及时间戳 |
| `params.json` | （自动生成）迭代层覆盖的阈值 |

### 输出

每次回复末尾展示指标卡片：

```
─── hallucination-watch ──────────────────────────────────
   输入: 847 | 输出: 1,203 | 总计: 2,050
   主观: 4 | 模糊差异: 76% | 冗余: 0
   风险: 0.01% | 阈值: 100% | 状态: 安全
──────────────────────────────────
```

纠错层发现错误时，在指标卡片后追加修正块：

```
─── hallucination-watch ──────────────────────────────────
   ... Metrics ...
──────────────────────────────────

[自我纠错 / Self-Correction]
 发现 1/3 条声明需修正:

 • 原: "法国的首都是里昂"
   正: "法国的首都是巴黎"

 修正率: 33% | 方法: A+B | B路径: 一致
──────────────────────────────────
```

### 目录结构

```
hallucination-watch/
├── SKILL.md                    # 模型指令
├── README.md                   # 本文件
├── scripts/
│   ├── calibrate_threshold.py  # Baseline 校准 (动态N)
│   ├── adapt_threshold.py      # EMA 自主迭代
│   ├── correction.py           # 声明优先级 + 选择机制
│   ├── count_tokens.py         # Token 统计
│   ├── fuzzy_match.py          # hash 截取 + 模糊比对
│   ├── calc_habit.py           # 习惯削面计算
│   ├── topic_embed.py          # 话题签名 + Jaccard 相似度
│   └── reference_material.py   # 材料存储 + 一致性检查
├── tools/
│   ├── compare_models.py       # 多模型离线对比
│   └── e2e_test.py             # 端到端测试
├── references/
│   └── algorithm-spec.md       # 完整技术说明
└── params/
    └── default.json            # 默认参数
```

### 开发路线

- **v1.0**：核心算法——主观计数、模糊比对、Token 追踪、决策公式 ✅
- **v2.0**：自主学习层——基于 EMA 和触发率反馈的动态阈值调整 ✅
- **v3.0**：自我纠错层——双方向验证（B：内部自治性，A：声明 Web Fetch）✅

### 局限性

| # | 说明 |
|---|------|
| 1 | **分数是相对值，不是概率。** 只与当前模型自身的基线比较，不是绝对的幻觉概率。 |
| 2 | **主观词≠幻觉。** 这是一个方向性信号，不是确定性判断。 |
| 3 | **跨会话比对受话题漂移影响。** 话题追踪已缓解但无法完全消除噪声。 |
| 4 | **方向 B 可能存在共同盲区。** 两条推理路径可能同时使用同一错误知识。 |
| 5 | **没有基准测试数据。** 准确率未经标注数据集验证。 |
| 6 | **设计为前置筛选器。** 不能替代针对关键内容的完整事实核查。 |
| 7 | **密度归一化假设线性关系。** 超短回复（<20 tokens）的密度值可能偏高。 |
| 8 | **参考材料受限于话题检测。** 仅在同话题连续 3 次对话后激活。 |
| 9 | **材料存储的是模型表述，不是验证后的事实。** 检测的是自我矛盾，不是事实错误。 |

### 许可

MIT
