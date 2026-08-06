---
name: hallucination-watch
description: "User-activated hallucination risk monitor for LLM conversations. Uses 6 behavioral proxy signals (keyword density, self-consistency, fuzzy match, material consistency, redundancy, habit profile) with EMA threshold adaptation. Per-session isolation. MCP tools available: hw_init/hw_check/hw_status/hw_reset."
metadata:
  requires: [jieba, mcp, pydantic]
  python: ">=3.9"
---

# Hallucination Watch

用户激活式幻觉风险监测器。基于 6 个行为代理信号 + EMA 阈值自适应，按会话隔离。

## 触发

用户说出"启动幻觉监测"或类似意思 → 调用 `hw_init` MCP 工具。

## MCP 工具

| Tool | Description |
|:---|:---|
| `hw_init` | 初始化/复用会话 + 写入 AGENTS.md 监测规则 |
| `hw_check` | 对回复执行 6 信号监测 + 可选纠错，返回 zone/risk_pct |
| `hw_status` | 查看累计状态和最近 3 轮摘要 |
| `hw_reset` | 重置全部数据 + 清理标记和 AGENTS.md 规则 |

## 6 信号

| Signal | Source | Description |
|:---|:---|:---|
| Keyword Density | `signal_keyword.py` | 绝对化表述 + 高危词 3 倍加权 |
| Self-Consistency | `signal_consistency.py` | Jaccard 相似度跨轮对比 |
| Fuzzy Match | `signal_fuzzy.py` | 指纹哈希跨轮匹配 |
| Material Consistency | `signal_material.py` | jieba 分词话题门控 + 矛盾检测 |
| Redundancy | `signal_redundancy.py` | 累计文本量线性增长 |
| Habit Profile | `signal_habit.py` | 字符位置 5-bin 分布 + anomaly |

## 决策

`risk_raw = kw×10 + cs + fz + mt + rd + ha`

`risk_pct = risk_raw / threshold × 100`

| Zone | Criteria | Action |
|:---|:---|:---|
| Safe | < 100% | 静默 |
| Mark | 100–250% | 展示卡片 |
| Verify | ≥ 250% | 展示卡片 |

## EMA 自适应

每 `adaptation_interval` 轮根据 `trigger_rate` 自动调整 `threshold`。高于目标范围则升高阈值（减少误报），低于则降低（减少漏报）。

## 自动纠错

`correction_enabled: true` 时，`hw_check` 在 `triggered=true` 下额外提取并排序高风险声明。默认关闭。

## 配置

`params/default.json`，18 个参数。核心可调：

| Parameter | Default | Purpose |
|:---|:---:|:---|
| threshold | 22 | 风险阈值 |
| correction_enabled | false | 自动纠错开关 |
| target_trigger_rate | 0.10 | EMA 目标触发率 |
| topic_similarity_threshold | 0.15 | 话题门控门槛 |
