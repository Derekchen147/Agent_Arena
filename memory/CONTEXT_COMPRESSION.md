# 上下文压缩策略

## 1. 压缩目标

### 1.1 核心目标
- **减少存储空间**: 目标减少50-70%的原始存储需求
- **保持信息完整性**: 保留90%以上的关键决策和行动信息
- **提高检索效率**: 压缩后的上下文应该更容易理解和检索
- **支持增量更新**: 能够高效地追加新信息而不重写整个文件

### 1.2 性能指标
- **压缩比**: 原始内容大小 / 压缩后大小 ≥ 2.0
- **信息保留率**: 关键信息保留率 ≥ 90%
- **处理延迟**: 单条消息压缩时间 ≤ 100ms
- **内存占用**: 压缩过程内存占用 ≤ 50MB

## 2. 压缩算法设计

### 2.1 多层压缩策略

#### 层1: 内容过滤
```
输入: 原始群聊消息
输出: 过滤后的消息流

过滤规则:
- 移除重复的问候语 ("hello", "hi", "good morning" 等)
- 移除无意义的确认 ("ok", "got it", "thanks" 等)
- 保留包含关键词的消息 (决定、任务、截止日期、同意、不同意等)
- 保留首次出现的新话题
```

#### 层2: 语义摘要
```
输入: 过滤后的消息
输出: 语义摘要

处理步骤:
1. 识别对话主题和子话题
2. 提取每个话题的核心观点
3. 识别决策点和行动项
4. 记录参与者的态度和倾向
5. 生成结构化摘要
```

#### 层3: 模式识别
```
输入: 语义摘要序列
输出: 行为模式和关系网络

识别内容:
- Agent 的沟通风格 (直接/委婉、详细/简洁)
- 决策倾向 (风险偏好、合作性)
- 专业领域和知识边界
- Agent 间的关系动态 (合作/竞争、信任度)
```

### 2.2 具体实现算法

#### 算法1: 基于关键词的重要性评分
```python
def calculate_message_importance(message):
    """计算消息重要性评分"""
    keywords = {
        "high": ["决定", "同意", "不同意", "任务", "截止", "紧急", "重要"],
        "medium": ["建议", "想法", "问题", "讨论", "考虑"],
        "low": ["好的", "谢谢", "明白", "收到"]
    }
    
    score = 0
    text = message.lower()
    
    for word in keywords["high"]:
        if word in text:
            score += 10
    for word in keywords["medium"]:
        if word in text:
            score += 5
    for word in keywords["low"]:
        if word in text:
            score -= 2
    
    # 长度惩罚（过长的消息可能包含冗余信息）
    if len(text) > 500:
        score = score * 0.8
    
    return max(score, 0)
```

#### 算法2: 语义相似度去重
```python
def remove_semantic_duplicates(messages, threshold=0.8):
    """移除语义相似的重复消息"""
    unique_messages = []
    embeddings = []
    
    for msg in messages:
        embedding = get_text_embedding(msg.content)
        
        # 检查是否与已有消息相似
        is_duplicate = False
        for existing_emb in embeddings:
            similarity = cosine_similarity(embedding, existing_emb)
            if similarity > threshold:
                is_duplicate = True
                break
        
        if not is_duplicate:
            unique_messages.append(msg)
            embeddings.append(embedding)
    
    return unique_messages
```

#### 算法3: 对话流压缩
```python
def compress_conversation_flow(messages):
    """压缩连续的对话流"""
    compressed = []
    current_topic = None
    topic_messages = []
    
    for msg in messages:
        topic = classify_message_topic(msg)
        
        if topic != current_topic and current_topic is not None:
            # 压缩当前话题
            summary = summarize_topic_messages(topic_messages)
            compressed.append(summary)
            topic_messages = []
        
        current_topic = topic
        topic_messages.append(msg)
    
    # 处理最后一个话题
    if topic_messages:
        summary = summarize_topic_messages(topic_messages)
        compressed.append(summary)
    
    return compressed
```

## 3. 压缩格式规范

### 3.1 标准压缩格式
```
[时间戳] [参与者] [重要性:高/中/低]
主题: {主题分类}
内容: {压缩后的内容}
决策: {相关决策，如果有}
行动项: {相关行动项，如果有}
行为模式: {观察到的行为特征}
```

### 3.2 示例对比

#### 原始群聊记录
```
[2026-02-26 10:00:00] Alice: 大家早上好！
[2026-02-26 10:00:05] Bob: 早上好！
[2026-02-26 10:00:10] Charlie: hi everyone
[2026-02-26 10:01:00] Alice: 我们需要讨论一下项目A的截止日期
[2026-02-26 10:01:30] Bob: 我觉得应该延期到下周五
[2026-02-26 10:02:00] Charlie: 我同意Bob的建议，延期比较合理
[2026-02-26 10:02:30] Alice: 好的，那我们就决定延期到下周五
[2026-02-26 10:03:00] Bob: 谢谢！
[2026-02-26 10:03:05] Charlie: 收到
```

#### 压缩后版本
```
[2026-02-26 10:01:00] Alice [重要性:高]
主题: 项目截止日期讨论
内容: Alice提出讨论项目A截止日期，Bob建议延期到下周五，Charlie表示同意
决策: 项目A截止日期延期至下周五
行动项: 更新项目计划
行为模式: Bob倾向于提供具体建议，Charlie支持团队共识
```

## 4. 动态调整策略

### 4.1 自适应压缩级别
- **高活跃度群聊**: 使用更强的压缩（保留核心决策）
- **低活跃度群聊**: 使用较弱的压缩（保留更多细节）
- **重要项目群聊**: 降低压缩强度，增加信息保留

### 4.2 学习型压缩
- 分析用户对压缩内容的反馈
- 调整关键词权重和重要性评分
- 优化语义相似度阈值
- 个性化压缩策略

## 5. 实现注意事项

### 5.1 技术约束
- **实时性要求**: 压缩过程不能显著延迟消息处理
- **资源限制**: 在有限的计算资源下运行
- **可逆性**: 某些场景下需要能够还原原始上下文

### 5.2 质量保证
- **人工验证**: 定期抽样检查压缩质量
- **A/B测试**: 比较不同压缩策略的效果
- **用户反馈**: 收集用户对压缩内容的满意度

### 5.3 错误处理
- **压缩失败**: 降级到原始存储，记录错误日志
- **数据损坏**: 实现校验和和恢复机制
- **边界情况**: 处理极端短/长消息、特殊字符等