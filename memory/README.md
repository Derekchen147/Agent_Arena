# OpenClaw 记忆系统设计文档

## 概述

这是一个为多 Agent 系统设计的记忆模块，基于 OpenClaw 的记忆逻辑。每个 Agent 都可以拥有独立的记忆存储，同时支持群聊上下文的压缩和优化。

## 核心设计理念

### 1. 双层记忆架构
- **长期记忆 (Long-term Memory)**: 存储重要决策、偏好、关键信息
- **短期记忆 (Short-term Memory)**: 记录日常交互、临时事件、具体对话

### 2. 安全与隐私
- 每个 Agent 的记忆相互隔离
- 敏感信息不外泄
- 群聊上下文与个人记忆分离

### 3. 主动维护
- 定期审查和清理记忆内容
- 提取重要信息到长期记忆
- 压缩和优化上下文占用

## 目录结构

```
memory/
├── README.md                 # 本设计文档
├── MEMORY_SPEC.md           # 记忆系统规范
├── PROMPTS.md               # 记忆相关的 Prompt 模板
├── AGENT_MEMORY_GUIDE.md    # Agent 记忆实现指南
├── CONTEXT_COMPRESSION.md   # 上下文压缩策略
└── examples/                # 使用示例
    ├── agent_memory_example.md
    └── group_chat_compression_example.md
```