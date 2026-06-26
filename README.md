# Hallucination Watch · 幻觉监测

> A low-cost, user-activated hallucination risk screening skill for LLM conversations.
> Uses 6 behavioral proxy signals with EMA threshold adaptation. Per-session isolation.
>
> 一款极低成本的幻觉检测与纠错 Skill，基于 6 个行为代理信号 + EMA 阈值自适应。
> 按会话隔离，支持 MCP 工具集成。

## Features / 特性

| English | Chinese |
|:---|:---|
| **6 signals**: keyword density, self-consistency, fuzzy match, material consistency, redundancy, habit profile | **6 信号监测**：关键词密度、自洽性、模糊匹配、素材一致性、冗余度、习惯画像 |
| **Powerful Chinese support**: jieba word segmentation + stop word filtering | **中文深度优化**：jieba 分词 + 停用词过滤 |
| **EMA threshold adaptation** | **EMA 阈值自适应** |
| **MCP integration**: 4 tools | **MCP 集成**：4 个工具 |
| **Idempotent init**: restart-safe | **幂等初始化**：重启安全 |
| **AGENTS.md management** | **AGENTS.md 自动管理** |
| **Atomic writes**: crash-safe | **原子写入**：崩溃安全 |

## Quick Start / 快速开始

### 1. Install / 安装

```bash
cp -r hallucination-watch ~/.config/opencode/skills/
```

### 2. Register MCP / 注册 MCP

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

## Architecture / 架构

```
hallucination-watch/
├── SKILL.md
├── README.md
├── params/default.json
├── scripts/
│   ├── hallucination_watch_mcp.py  ← MCP server
│   ├── monitor.py                  ← CLI entry
│   ├── check_compliance.py
│   ├── signal_*.py                 ← 9 signal modules
└── sessions/
```

## License / 许可证

MIT