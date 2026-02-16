# 主流 AI 大模型 API 价格汇总（每百万 Token）

> 数据收集时间：2025年2月。价格可能随时调整，请以各厂商官方页面为准。

---

## 一、美国及国际主流模型（美元 / 百万 tokens）

### 1. OpenAI

| 模型 | 输入 (Input) | 缓存输入 (Cached) | 输出 (Output) |
|------|--------------|-------------------|---------------|
| **GPT-5.2** | $1.75 | $0.175 | $14.00 |
| **GPT-5.2 Pro** | $21.00 | — | $168.00 |
| **GPT-5 mini** | $0.25 | $0.025 | $2.00 |
| **GPT-4.1**（微调） | $3.00 | $0.75 | $12.00 |
| **GPT-4.1 mini**（微调） | $0.80 | $0.20 | $3.20 |
| **GPT-4.1 nano**（微调） | $0.20 | $0.05 | $0.80 |
| **Realtime: gpt-realtime** | $4.00 | $0.40 | $16.00 |
| **Realtime: gpt-realtime-mini** | $0.60 | $0.06 | $2.40 |

- 来源：[OpenAI API Pricing](https://openai.com/api/pricing/)
- Batch API：输入输出均可享约 50% 折扣

---

### 2. Anthropic（Claude）

| 模型 | 输入 (Input) | 输出 (Output) |
|------|--------------|---------------|
| **Claude 4.5 Haiku** | $1.00 | $5.00 |
| **Claude 4.5 Sonnet** | $3.00 | $15.00 |
| **Claude 4.5 Opus** | $5.00 | $25.00 |
| Claude Haiku 3.5 | $0.80 | $4.00 |
| Claude Sonnet 4 | $3.00 | $15.00 |
| Claude Opus 4.1 | $15.00 | $75.00 |

- 来源：[Anthropic Pricing](https://docs.anthropic.com/en/docs/about-claude/pricing)
- 支持 Prompt Caching，缓存命中可低至约 0.1× 输入价；Batch API 约 50% 折扣

---

### 3. Google（Gemini）

| 模型 | 输入 (Input) | 输出 (Output) | 备注 |
|------|--------------|---------------|------|
| **Gemini 3 Pro Preview** | $2.00 / $4.00* | $12.00 / $18.00* | * 长上下文 >200K 更贵 |
| **Gemini 3 Flash Preview** | $0.50 | $3.00 | |
| **Gemini 2.5 Pro** | $1.25 | $10.00 | |
| **Gemini 2.5 Flash** | $0.30 | $2.50 | |
| **Gemini 2.5 Flash-Lite** | $0.10 | $0.40 | |

- 来源：[Gemini API Pricing](https://ai.google.dev/gemini-api/docs/pricing)
- 支持 Batch（约 50% 折扣）、Context Caching（最高约 90% 节省）

---

### 4. DeepSeek（国际 API，美元）

| 模型 | 输入 (Cache Hit) | 输入 (Cache Miss) | 输出 (Output) |
|------|------------------|-------------------|---------------|
| **DeepSeek-Chat (V3.2)** | $0.028 | $0.28 | $0.42 |
| **DeepSeek-Reasoner (V3.2)** | $0.14 | $0.55 | $2.19 |

- 来源：[DeepSeek API Pricing](https://api-docs.deepseek.com/quick_start/pricing/)
- 上下文 128K；有时段折扣（UTC 16:30–00:30 约 50–75% 优惠）

---

### 5. Meta（Llama）

| 模型 | 输入 (Input) | 输出 (Output) |
|------|--------------|---------------|
| Llama 3.2 3B Instruct | $0.02 | $0.02 |
| Llama 3.1 8B Instruct | $0.02 | $0.05 |
| Llama 3.3 70B Instruct | $0.10 | $0.32 |
| Llama 4 Scout | $0.08 | $0.30 |
| **Llama 4 Maverick** | $0.15 | $0.60 |
| Llama 3.1 405B Instruct | $3.50 | $3.50 |

- 来源：Meta Llama API 及第三方汇总（以官方为准）

---

### 6. Mistral AI

| 模型 | 输入 (Input) | 输出 (Output) |
|------|--------------|---------------|
| **Mistral Large 24-11** | $2.00 | $6.00 |
| **Mistral Large 3** | $0.50 | $1.50 |
| **Mistral Medium 3** | $0.40 | $2.00 |
| **Mistral Small 3.1** | $0.10 | $0.30 |
| **Mistral NeMo / Nemo** | $0.02–0.15 | $0.04–0.15 |
| Devstral 2 | $0.05 | $0.22 |

- 来源：[Mistral Pricing](https://docs.mistral.ai/deployment/ai-studio/pricing)

---

### 7. Cohere

- **Command R7B** 等：约 **$0.0375 输入 / $0.15 输出** 每百万 tokens（公开报道）
- 生产环境多为定制报价，需联系销售或通过控制台申请 Production API

---

## 二、中国主流模型（人民币 元 / 百万 tokens）

### 1. 阿里云 · 通义千问

| 模型 | 输入 | 输出 | 备注 |
|------|------|------|------|
| **qwen-turbo** | ¥2 | ¥6 | 通用轻量 |
| **qwen-plus** | ¥4 | ¥12 | 平衡 |
| **qwen-max** | ¥40 | ¥12 | 旗舰 |
| **qwen-long** | ¥0.5 | ¥2 | 超长文本，性价比高 |

- 来源：阿里云通义千问 API 文档及公开报道

---

### 2. 百度 · 文心一言（ERNIE）

| 说明 | 价格/备注 |
|------|------------|
| 文心 4.0 等 | 公开报道约 **¥120/百万 tokens 输入** 量级；部分模型有免费/限时优惠 |
| 具体价格 | 以 [百度智能云千帆](https://cloud.baidu.com/product/wenxinworkshop) 当前价格为准 |

---

### 3. 智谱 AI · GLM

| 模型 | 输入 | 输出 | 备注 |
|------|------|------|------|
| **GLM-4** | ¥100 | ¥100 | 旗舰（曾有降价至约 ¥30 等） |
| **GLM-4-Plus** | ¥5 | ¥5 | 降价后约 5 元/百万 |
| **GLM-4-Flash** | 约 ¥0.06 起 | — | 低价档 |
| **GLM-3-Turbo** | ¥1 | ¥1 | 约 1 元/百万（有报道最低约 ¥0.6） |
| **GLM-4V**（多模态） | 约 ¥30–100 | 约 ¥30–100 | 以官网为准 |

- 来源：智谱开放平台及公开报道（价格战期间变动较大）

---

### 4. 月之暗面 · Kimi（Moonshot）

| 模型 | 价格（元/百万 tokens） | 备注 |
|------|------------------------|------|
| **moonshot-v1-32k** | 约 ¥5 | 32K 上下文 |
| **moonshot-v1-128k** | 约 ¥60 | 128K 上下文 |

- 来源：月之暗面 API 文档及第三方汇总

---

### 5. 腾讯 · 混元

| 模型 | 价格（元/百万 tokens） | 备注 |
|------|------------------------|------|
| **混元 Lite** | 约 ¥5（输入输出同价） | 入门/轻量 |
| 其他档位 | 以腾讯云混元 API 文档为准 | |

---

### 6. 字节跳动 · 豆包（Doubao）

| 类型 | 价格（元/百万 tokens） |
|------|------------------------|
| 基础版 | 约 ¥0.3–0.8 |
| 高级版 | 约 ¥5–9 |

- 来源：公开报道及火山引擎/豆包 API 文档

---

### 7. DeepSeek（中国区 / 人民币）

| 模型 | 输入 | 输出 | 备注 |
|------|------|------|------|
| **DeepSeek V3** 等 | 约 ¥0.5–2（含缓存约 ¥0.5） | 约 ¥8 | 国内价格以官网/控制台为准 |

- 国内与国际定价可能不同，请以 [DeepSeek 开放平台](https://platform.deepseek.com/) 为准。

---

## 三、价格区间速览（每百万 tokens）

| 档次 | 美国（USD） | 中国（CNY） |
|------|-------------|-------------|
| **入门/极低价** | DeepSeek $0.28/$0.42，Gemini Flash-Lite $0.10/$0.40，Mistral Nemo $0.02/$0.04 | 通义 qwen-long ¥0.5/¥2，智谱 Flash ¥0.06 起，豆包基础 ¥0.3–0.8 |
| **中端** | GPT-5 mini $0.25/$2，Claude Haiku $1/$5，Gemini 2.5 Flash $0.30/$2.50 | 通义 turbo/plus，智谱 GLM-3-Turbo/Plus，混元 Lite，Kimi 32k 约 ¥5 档 |
| **旗舰** | GPT-5.2 $1.75/$14，Claude Sonnet $3/$15，Gemini Pro $1.25–2/$10–12 | 通义 max，智谱 GLM-4，文心 4.0 等 |

---

## 四、使用与更新说明

1. **计费单位**：未特别说明处均为「每百万 tokens」；多数厂商对输入、输出分开计费，部分有缓存价、批量价。
2. **汇率**：美元按查询时汇率折算人民币仅供参考，实际以各平台当地货币报价为准。
3. **更新**：定价会频繁调整（尤其国内价格战），使用前请务必查看：
   - [OpenAI Pricing](https://openai.com/api/pricing/)
   - [Anthropic Pricing](https://docs.anthropic.com/en/docs/about-claude/pricing)
   - [Google Gemini Pricing](https://ai.google.dev/gemini-api/docs/pricing)
   - [DeepSeek Pricing](https://api-docs.deepseek.com/quick_start/pricing/)
   - 各中国厂商的开放平台/云控制台定价页

若你希望把某一家或某一模型的「最新一次核实日期」或「官方链接」单独列在文档里，可以说明厂商/模型名，我可以按你的结构再补一版。
