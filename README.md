# Hallucination Watch / 幻觉监测

[English](#english) | [中文](#中文)

---

## English

### Overview

**Hallucination Watch** is an opencode skill that screens LLM conversations for hallucination risk at low cost. It uses behavioral proxy signals (subjective language, cross-session consistency) to estimate risk. It stays silent during safe conversations and only alerts when risk is detected.

### How It Works

| Signal | Description |
|--------|-------------|
| **Subjective Keywords** | Counts assertive words that correlate with overconfidence |
| **Cross-Session Fuzzy Match** | Compares random character samples across conversations |
| **Token Redundancy** | Tracks cumulative token usage. Longer conversations get additional scrutiny. |

### Research Support

The token redundancy counter is grounded in published research:
- **Lost in the Middle** (Liu et al., TACL 2023): Model accuracy drops as context expands
- **Limits of Long-Context Reasoning** (ICLR 2026): Longer cumulative tokens correlate with lower success rates
- **U-NIAH** (2025): Long context leads to systematic hallucination patterns

The tokens-per-increment ratio is self-adapted by the learning layer.

## 中文

### 理论依据

Token 冗余计数器的设计基于已发表的研究：
- **Lost in the Middle** (TACL 2023): 上下文长度增长导致模型准确率下降
- **Limits of Long-Context Reasoning** (ICLR 2026): 累计 token 越多，成功率越低
- **U-NIAH** (2025): 长上下文导致系统性幻觉模式

每百万 token 的冗余加分由学习层自动调参。
