<div align="center">

# MindForge Studio

### Open-source Multi-Agent Salon for Real-World Decisions

<p>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/status-active-success" alt="Status">
  <img src="https://img.shields.io/badge/interface-Web%20%7C%20CLI-orange" alt="Interface">
</p>

<p>
  <b>让多个 Agent 先充分碰撞，再给出真正可执行的结论。</b>
</p>

<p>
  <img src="docs/assets/mindforge-logo.png" alt="MindForge Studio Logo" width="300">
</p>

</div>

---

## ✨ What is MindForge Studio?

MindForge Studio 是一个“多角色自由沙龙”系统。  
它不是传统的单轮问答，也不是固定模板式输出，而是让多个 Agent 围绕同一个问题进行**质疑、支持、补充、推进与收束**，最终生成一份更接近真实决策过程的可执行结论。

你可以把它理解为一个面向现实问题的 **multi-agent deliberation studio**：

- 不强调“谁说得最像”，而强调**多视角碰撞**
- 不追求流水线式套话，而强调**自然讨论过程**
- 不只给一个总答案，而会保留**每个 Agent 的关键判断**

---

## 🚀 Features

- **自由沙龙式讨论**：不是 rigid workflow，而是真正带互动张力的多 Agent 对话
- **默认多轮发言**：每位成员默认至少发言 5 次，可配置
- **可控互动风格**：支持用户自定义发言长度、互动风格、成员名单
- **更强结论聚合**：最终不仅输出总方案，还会提炼每个 Agent 的具体观点
- **互动关系可视化**：支持 challenge / resonance 等互动边可视化
- **Web + CLI 双入口**：既可本地网页运行，也可命令行直接调度

---

## 📚 Table of Contents

- [✨ What is MindForge Studio?](#-what-is-mindforge-studio)
- [🚀 Features](#-features)
- [🖼️ Preview](#️-preview)
- [🧪 Real Cases](#-real-cases)
- [⚡ Quick Start](#-quick-start)
- [🛠️ User Controls](#️-user-controls)
- [🏗️ Architecture](#️-architecture)
- [📂 Output Structure](#-output-structure)
- [❓ FAQ](#-faq)
## Acknowledgements

- [nuwa-skill](https://github.com/alchaincyf/nuwa-skill): we reused ideas and assets for skill distillation.
- [ClawTeam](https://github.com/HKUDS/ClawTeam): the inter-agent collaboration strategy in this project is inspired by its coordination patterns.

---

- [🗺️ Roadmap](#️-roadmap)
- [📄 License](#-license)

---

## 🖼️ Preview

### Web UI
```text
[ Screenshot Placeholder ]
docs/assets/web-ui.png
```

### Discussion Graph
```text
[ Visualization Placeholder ]
docs/assets/interaction-graph.png
```

### Output Report
```text
[ Report Placeholder ]
docs/assets/report-preview.png
```

---

## 🧪 Real Cases

### 1. 中国风 × 赛博朋克 × 粤语歌

- 场景目录：`outputs/scenario-20260408-182643/`
- 入选角色：麦浚龙、张叔平、黄霑、谭盾、邓紫棋、黄耀明

**输出特点：**
- 完整创作框架（歌名方向、风格比例、意象池、制作约束）
- 汇总各 Agent 在句法、咬字、hook 长度、声场编排上的具体建议

---

### 2. 村上春树 + 王阳明 + 张爱玲 + 巴菲特婚恋建议

- 场景目录：`outputs/scenario-20260409-031622/`
- 入选角色：村上春树、王阳明、张爱玲、巴菲特（严格锁定）

**输出特点：**
- 每位角色都有具体判断标准（边界、责任、风险、修复机制）
- 不只是“鸡汤总结”，而是可验证的判断与行动建议

---

### 3. 贫困山区中学生走体育，100 万如何配置

- 场景目录：`outputs/scenario-20260409-032634/`
- 入选角色：李宁、邓亚萍、谷爱凌、张桂梅、苏炳添、姚明

**输出特点：**
- 资金配置 + 训练路径 + 学业兜底联合方案
- 明确风险线、预算分层与窗口期取舍

---

## ⚡ Quick Start

### 1) Install

```bash
python -m pip install -e .
```

### 2) Start Web UI

```bash
python -m celebrity_studio.api_server
```

Open: `http://localhost:8787`

### 3) Run in CLI (auto role selection)

```bash
python scripts/run_studio.py \
  --query "我想弄一个中国风与赛博朋克交织的粤语歌" \
  --team-size 6 \
  --language zh-CN \
  --provider-type codex_cli \
  --provider-model gpt-5.3-codex \
  --provider-timeout-s 300 \
  --selection-mode auto
```

### 4) Run in CLI (strict role selection)

```bash
python scripts/run_studio.py \
  --query "村上春树、王阳明、张爱玲、巴菲特一起给当代25岁的人做婚恋建议" \
  --team-size 4 \
  --language zh-CN \
  --provider-type codex_cli \
  --provider-model gpt-5.3-codex \
  --provider-timeout-s 300 \
  --selection-mode strict \
  --include-celebrities "村上春树,王阳明,张爱玲,巴菲特"
```

---

## 🛠️ User Controls

你可以在 Web 界面开局配置，也可以通过 runtime JSON 传入：

| Parameter | Description | Example |
|---|---|---|
| `discussion.min_turns_per_member` | 每位成员最少发言次数 | `5` |
| `discussion.turn_length` | 发言长度控制 | `brief \| standard \| long \| extended` |
| `discussion.interaction_style` | 用户自定义互动风格 | `自然 / 随性 / 沙龙化` |

---

## 🏗️ Architecture

### 1) Pipeline

1. Scenario 解析  
2. 候选检索（在线检索 + fallback）  
3. 角色选择（覆盖度 + 互补性 + 冲突生产力）  
4. 技能蒸馏（每个角色独立 skill）  
5. Studio 编排（多 Agent 会话）  
6. 自由沙龙辩论 + 主持收束  
7. 输出报告、JSON、互动图  

---

### 2) Debate Engine

- 阶段：
  - `salon-open`
  - `salon-flow`
  - `salon-pulse`
  - `salon-synthesis`
- 默认每位成员至少 5 轮发言
- 支持 `challenge / support / question / synthesize` 等自然互动动作
- 最终会提取“各 Agent 关键观点汇总”

---

### 3) Final Summary Enhancer

- 从真实对话中抽取高价值句（数字、方法、约束、风险、取舍）
- 避免空转式过渡语（如“我先接一下”“我回应一下”）污染总结
- 保障 Final Task Answer 不是空泛口号，而是带细节的行动方案

---

### 4) Stability Strategy

- `codex_cli` 支持更长超时（建议 `--provider-timeout-s 300`）
- 发生大面积生成失败时快速中断并给出明确原因
- 避免出现“全是错误文本”的伪总结输出

---

## 📂 Output Structure

每次运行会生成如下文件：

```text
outputs/<scenario-id>/
├── scenario.json
├── selection.json
├── skills.json
├── studio.json
├── debate.json
├── result.json
└── report.md
```

---

## ❓ FAQ

### Q1. 为什么会出现 `Codex CLI timed out` / `stream disconnected`？

通常是以下原因之一：

- 网络链路不稳定
- 代理配置异常
- 账号额度限制
- provider timeout 设置过低

**建议：**
- 检查 `HTTP_PROXY / HTTPS_PROXY / ALL_PROXY`
- 提高 `provider-timeout-s`
- 确认 `codex login status`
- 额度恢复后再重跑

---

### Q2. 为什么最终总结太泛？

MindForge Studio 已提供“按 Agent 提取价值句”的总结器。  
你也可以进一步提高：

- `min_turns_per_member`
- `turn_length=long/extended`
- 在 `interaction_style` 中明确要求“给出具体、可执行观点”

---

## 🗺️ Roadmap

- [ ] 增加更多可视化面板
- [ ] 支持更丰富的 Agent 互动模式
- [ ] 提升角色检索与匹配质量
- [ ] 支持更多 provider / model backend
- [ ] 增加更完整的 benchmark cases
- [ ] 发布更完善的 demo assets

---

## 📄 License

MIT (or your preferred license)
