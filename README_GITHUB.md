<div align="center">

# MindForge Studio
### Open-source Multi-Agent Salon for Real-World Decisions

![MindForge Studio Logo](docs/assets/mindforge-logo.png)

</div>

MindForge Studio 是一个“多角色自由沙龙”系统：  
不是单向陈述，而是多 Agent 互相质疑、支持、补充、收束，最后输出可执行结论。

---

## 为什么是 MindForge Studio

- 默认自由交流，不走固定模板话术
- 默认每位成员至少发言 5 次（可配置）
- 支持用户开局定义互动风格、发言长度、成员名单
- 最终结论不仅有总方案，还会汇总每个 Agent 的具体观点
- 支持可视化互动图（challenge / resonance edges）

---

## 三个实测案例（当前输出样例）

### 1) 中国风 × 赛博朋克 × 粤语歌
- 场景目录：`outputs/scenario-20260408-182643/`
- 入选角色：麦浚龙、张叔平、黄霑、谭盾、邓紫棋、黄耀明
- 输出特点：
  - 完整创作框架（歌名方向、风格比例、意象池、制作约束）
  - 汇总各 Agent 的句法、咬字、hook 长度、声场编排等具体建议

### 2) 村上春树 + 王阳明 + 张爱玲 + 巴菲特婚恋建议
- 场景目录：`outputs/scenario-20260409-031622/`
- 入选角色：村上春树、王阳明、张爱玲、巴菲特（严格锁定）
- 输出特点：
  - 每位角色有具体判断标准（边界、责任、风险、修复机制）
  - 不是“鸡汤总结”，而是可验证的判断与行动建议

### 3) 贫困山区中学生走体育，100 万如何配置
- 场景目录：`outputs/scenario-20260409-032634/`
- 入选角色：李宁、邓亚萍、谷爱凌、张桂梅、苏炳添、姚明
- 输出特点：
  - 资金配置 + 训练路径 + 学业兜底联合方案
  - 明确风险线、预算分层、窗口期取舍

---

## 快速开始

### 1. 安装
```bash
python -m pip install -e .
```

### 2. 启动 Web
```bash
python -m celebrity_studio.api_server
```
打开：`http://localhost:8787`

### 3. CLI 运行（Codex CLI）
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

### 4. CLI 运行（严格指定角色）
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

## 用户用法（你可控的参数）

- `discussion.min_turns_per_member`：每人最少发言次数（默认 5）
- `discussion.turn_length`：`brief | standard | long | extended`
- `discussion.interaction_style`：用户自定义互动风格（自然、随性、沙龙化）

你可以在 Web 界面开局配置，也可以在 runtime JSON 中传入。

---

## 技术实现细节（核心）

### 1) Pipeline
1. Scenario 解析  
2. 候选检索（在线检索 + fallback）  
3. 角色选择（覆盖度 + 互补性 + 冲突生产力）  
4. 技能蒸馏（每个角色独立 skill）  
5. Studio 编排（多 Agent 会话）  
6. 自由沙龙辩论 + 主持收束  
7. 输出报告、JSON、互动图

### 2) Debate Engine（自由沙龙）
- 阶段：`salon-open -> salon-flow -> salon-pulse -> salon-synthesis`
- 默认每位成员至少 5 轮发言
- 支持 challenge/support/question/synthesize 等自然互动动作
- 最终会提取“各 Agent 关键观点汇总”

### 3) 最终总结增强
- 从真实对话中抽取高价值句（数字、方法、约束、风险、取舍）
- 避免空转过渡语（如“我先接/我回应”）占据总结
- 保障 Final Task Answer 不是笼统口号，而是可落地细节

### 4) 稳定性策略
- `codex_cli` 支持更长超时（建议 `--provider-timeout-s 300`）
- 发生大面积生成失败时快速中断并报出明确原因（网络/超时/额度）
- 避免生成“全是错误文本”的假总结

---

## 输出结构

每次运行会生成：
- `scenario.json`
- `selection.json`
- `skills.json`
- `studio.json`
- `debate.json`
- `result.json`
- `report.md`

路径示例：  
`outputs/<scenario-id>/`

---

## 常见问题

### Q1: 为什么会出现 `Codex CLI timed out` / `stream disconnected`？
通常是网络链路不稳定或代理配置问题，也可能是账号额度限制。  
建议：
- 检查 `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY`
- 提高 `provider-timeout-s`
- 确认 `codex login status`
- 额度恢复后重跑

### Q2: 为什么最终总结太泛？
MindForge Studio 已提供“按 Agent 提取价值句”的总结器；你也可提高：
- `min_turns_per_member`
- `turn_length=long/extended`
- 在 `interaction_style` 中强调“要具体可执行观点”

---

## License

MIT (or your preferred license)
