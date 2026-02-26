# Agent 记忆实现指南

## 1. 目录结构设计

每个 Agent 应该拥有独立的记忆目录结构：

```
agents/{agent_id}/
├── memory/
│   ├── MEMORY.md                 # Agent 长期记忆
│   ├── memory/                   # 短期记忆目录
│   │   └── YYYY-MM-DD.md        # 每日记忆文件
│   └── group_context/           # 群聊上下文（可选）
│       └── {group_id}/
│           ├── YYYY-MM-DD.md    # 群聊每日记录
│           └── agent_profiles.md # 其他 Agent 特征
└── config/
    └── memory_config.json       # 记忆系统配置
```

## 2. 核心实现逻辑

### 2.1 会话初始化流程

```python
def initialize_session(agent_id, session_type, context=None):
    """
    初始化 Agent 会话的记忆加载
    
    Args:
        agent_id: Agent 唯一标识
        session_type: "direct" | "group"
        context: 上下文信息（群聊ID等）
    """
    memory_base = f"agents/{agent_id}/memory"
    
    # 加载长期记忆（仅限直接对话）
    if session_type == "direct":
        long_term_memory = load_file(f"{memory_base}/MEMORY.md")
    else:
        long_term_memory = None  # 群聊中不加载个人长期记忆
    
    # 加载短期记忆（最近2天）
    recent_dates = get_recent_dates(days=2)
    short_term_memories = []
    for date in recent_dates:
        file_path = f"{memory_base}/memory/{date}.md"
        if file_exists(file_path):
            short_term_memories.append(load_file(file_path))
    
    # 加载群聊上下文（如果是群聊）
    group_context = None
    if session_type == "group" and context.get("group_id"):
        group_id = context["group_id"]
        recent_group_dates = get_recent_dates(days=7)  # 群聊保留更长时间
        group_context = []
        for date in recent_group_dates:
            file_path = f"{memory_base}/group_context/{group_id}/{date}.md"
            if file_exists(file_path):
                group_context.append(load_file(file_path))
    
    return {
        "long_term": long_term_memory,
        "short_term": short_term_memories,
        "group_context": group_context
    }
```

### 2.2 记忆写入逻辑

```python
def write_memory(agent_id, content, memory_type="short", metadata=None):
    """
    写入记忆内容
    
    Args:
        agent_id: Agent 唯一标识
        content: 要写入的内容
        memory_type: "long" | "short" | "group"
        metadata: 附加元数据（时间戳、重要性等）
    """
    memory_base = f"agents/{agent_id}/memory"
    current_date = get_current_date()
    
    if memory_type == "long":
        # 长期记忆 - 追加到 MEMORY.md
        file_path = f"{memory_base}/MEMORY.md"
        append_to_file(file_path, f"\n- {content}")
        
    elif memory_type == "short":
        # 短期记忆 - 写入当日文件
        file_path = f"{memory_base}/memory/{current_date}.md"
        timestamp = get_current_timestamp()
        entry = f"- [{timestamp}] {content}"
        append_to_file(file_path, entry)
        
    elif memory_type == "group":
        # 群聊上下文 - 需要 group_id
        group_id = metadata.get("group_id")
        if not group_id:
            raise ValueError("Group context requires group_id")
            
        file_path = f"{memory_base}/group_context/{group_id}/{current_date}.md"
        ensure_directory_exists(os.path.dirname(file_path))
        
        # 应用上下文压缩
        compressed_content = compress_context(content, metadata)
        append_to_file(file_path, compressed_content)
```

### 2.3 上下文压缩实现

```python
def compress_context(raw_content, metadata):
    """
    压缩群聊上下文
    
    Args:
        raw_content: 原始群聊内容
        metadata: 包含参与者、时间等信息
        
    Returns:
        压缩后的上下文字符串
    """
    # 提取核心信息
    core_info = extract_core_information(raw_content)
    
    # 识别行为模式
    behavior_patterns = identify_behavior_patterns(metadata.get("participants", []))
    
    # 生成摘要
    summary = generate_summary(core_info, behavior_patterns)
    
    # 添加元数据
    compressed = f"[{metadata['timestamp']}] {metadata['participant']}: {summary}"
    
    # 标记重要性
    importance = assess_importance(core_info)
    compressed += f" [重要性: {importance}]"
    
    return compressed
```

## 3. 配置管理

### 3.1 记忆系统配置文件

```json
{
  "memory_retention": {
    "short_term_days": 30,
    "group_context_days": 90,
    "long_term_indefinite": true
  },
  "compression": {
    "enabled": true,
    "token_limit_per_message": 200,
    "similarity_threshold": 0.8,
    "important_keywords": ["决定", "同意", "不同意", "任务", "截止"]
  },
  "privacy": {
    "group_chat_long_memory_access": false,
    "sensitive_data_filtering": true,
    "external_sharing_requires_consent": true
  },
  "maintenance": {
    "heartbeat_frequency_minutes": 30,
    "auto_cleanup_enabled": true,
    "backup_frequency_hours": 24
  }
}
```

### 3.2 动态配置更新

```python
def update_memory_config(agent_id, config_updates):
    """动态更新记忆系统配置"""
    config_path = f"agents/{agent_id}/config/memory_config.json"
    current_config = load_json(config_path)
    updated_config = merge_configs(current_config, config_updates)
    save_json(config_path, updated_config)
    
    # 重新初始化记忆系统
    reinitialize_memory_system(agent_id, updated_config)
```

## 4. 性能优化建议

### 4.1 文件系统优化
- 使用 SSD 存储记忆文件
- 定期清理过期文件
- 实现文件分片存储（大文件）

### 4.2 内存缓存策略
- 缓存最近访问的记忆片段
- 实现 LRU 缓存淘汰策略
- 监控内存使用情况

### 4.3 并发控制
- 文件锁防止并发写入冲突
- 异步写入提高响应速度
- 批量操作减少 I/O 开销

## 5. 测试与验证

### 5.1 单元测试要点
- 记忆写入的原子性
- 文件路径安全性
- 压缩算法准确性
- 隐私保护有效性

### 5.2 集成测试场景
- 多 Agent 同时写入同一群聊上下文
- 长期运行的记忆文件增长控制
- 灾难恢复和备份验证
- 边界条件处理（磁盘满、权限错误等）

## 6. 扩展性考虑

### 6.1 插件化设计
- 支持自定义压缩算法
- 可插拔的记忆存储后端
- 扩展的记忆类型支持

### 6.2 分布式部署
- 跨节点记忆同步
- 一致性保证机制
- 网络分区处理策略