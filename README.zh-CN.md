[English](README.md) | [简体中文](README.zh-CN.md)

<div align="center">

# MindForge Studio

### 面向多名人人格的开源多 Agent 讨论工作台

<p>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/status-active-success" alt="Status">
  <img src="https://img.shields.io/badge/interface-Web%20%7C%20CLI-orange" alt="Interface">
</p>

<p>
  <img src="docs/assets/mindforge-logo.png" alt="MindForge Studio Logo" width="220">
</p>

</div>

MindForge Studio 不是一个随便找几个 AI 角色来聊天的系统。
它会先从不同名人、创作者、企业家、思想者、运动员和历史人物身上提取他们各自擅长的 skill，比如审美判断、商业决策、表达洞察、执行推进，再根据用户给出的具体场景，动态挑选真正对题的人进入同一个工作室。

用户给的是场景，不是抽象标签。
系统不会默认塞进“老师 / 顾问 / 导演 / 分析师”这类泛化角色，而是针对每个问题重新选人：做升学规划，可以请张雪峰、俞敏洪；做歌曲创作，可以请林夕、周杰伦；做品牌、传播、投资、谈判、教育、创作、体育训练、历史判断，也都应该换一组真正契合主题的人。

更重要的是，这也不是“每个 Agent 各说各话，然后拼成一页报告”。
它更像一场自由沙龙式的 deep research：有人先提出判断，有人质疑前提，有人补充案例，有人从另一个时代或领域反驳，最后再逐步收束成更可执行的结论。

## 它最特别的地方

- 先从真实人物中蒸馏 skill，而不是套用抽象角色模板
- 再按场景动态选人，让每次讨论都重新组局，而且人必须对题
- 让 Agent 之间质疑、补充、反驳、推进，而不是并排输出几段意见
- 最终产出的是更接近真实决策过程的可执行结论，而不只是漂亮措辞

## 它能做什么

- 从真实人物身上提取可讨论的 skill 档案，而不是直接套固定身份
- 按场景动态挑选真正契合问题的名人 / 人物组合
- 用自由沙龙式深度讨论替代僵硬工作流
- 支持配置团队人数、发言轮次、发言长度和互动风格
- 同时输出最终结论和每个 Agent 的关键观点，而不是简单拼接发言
- 提供本地 Web UI 和 CLI 两种入口
- 支持可选的公网门户与视频生成流程

## 示例场景

### 1. 中国风 x 赛博朋克 x 粤语歌

- 输出目录：`outputs/scenario-20260408-182643/`
- 示例角色：麦浚龙、张叔平、黄霑、谭盾、邓紫棋、黄耀明
- 典型结果：形成包含歌名方向、风格比例、意象池、制作约束的完整创作框架

### 2. 多视角婚恋建议

- 输出目录：`outputs/scenario-20260409-031622/`
- 示例角色：村上春树、王阳明、张爱玲、巴菲特
- 典型结果：给出明确判断标准、风险边界和可执行建议，而不是泛泛而谈

### 3. 贫困山区学生体育培养预算配置

- 输出目录：`outputs/scenario-20260409-032634/`
- 示例角色：李宁、邓亚萍、谷爱凌、张桂梅、苏炳添、姚明
- 典型结果：生成资金配置、训练路径和学业兜底结合的方案

## 快速开始

### 1. 安装

```bash
python -m pip install -e .
```

### 2. 配置环境变量

把 `.env.example` 复制为 `.env`，至少配置：

- `OPENAI_API_KEY`

常见可选项：

- `OPENAI_BASE_URL`
- `PUBLIC_PROVIDER_API_KEY`
- `PUBLIC_PROVIDER_BASE_URL`
- `YUNWU_API_KEY`

### 3. 启动本地 Web 服务

```bash
mindforge-studio-api
```

或者：

```bash
python -m celebrity_studio.api_server
```

打开：

- `http://127.0.0.1:8787/`
- `http://127.0.0.1:8787/public`：可选的公网入口
- `http://127.0.0.1:8787/api/health`：健康检查

### 4. 用 CLI 运行

```bash
python scripts/run_studio.py \
  --query "我想设计一个把中国风和赛博朋克融合起来的粤语歌概念。" \
  --team-size 6 \
  --language zh-CN \
  --provider-type codex_cli \
  --provider-model gpt-5.3-codex \
  --provider-timeout-s 300 \
  --selection-mode auto
```

指定固定角色：

```bash
python scripts/run_studio.py \
  --query "让村上春树、王阳明、张爱玲和巴菲特一起给当代 25 岁的人做婚恋建议。" \
  --team-size 4 \
  --language zh-CN \
  --provider-type codex_cli \
  --provider-model gpt-5.3-codex \
  --provider-timeout-s 300 \
  --selection-mode strict \
  --include-celebrities "村上春树,王阳明,张爱玲,巴菲特"
```

> 命名说明：项目品牌名是 MindForge Studio，但内部 Python 包名仍然保留为 `celebrity_studio` 以兼容现有代码。

## 可控参数

这些参数既可以从 Web UI 配置，也可以通过 runtime JSON 传入：

- `discussion.min_turns_per_member`
- `discussion.turn_length`：`brief | standard | long | extended`
- `discussion.interaction_style`
- `selection_mode`：`auto | prefer | strict`

## 工作流程

1. 解析场景问题，以及它真正需要什么样的判断力。
2. 检索候选人物及其蒸馏后的 skill 档案。
3. 根据 skill 匹配度、覆盖度、互补性和有效冲突选择团队。
4. 把这些 skill 转成可讨论的 Agent 设定。
5. 运行自由沙龙式多 Agent 讨论。
6. 汇总最终结论并提炼角色级观点。
7. 输出 JSON 结果和 Markdown 报告。

## 输出结构

每次运行都会在 `outputs/<scenario-id>/` 下生成：

- `scenario.json`
- `selection.json`
- `skills.json`
- `studio.json`
- `debate.json`
- `result.json`
- `report.md`

## 文档

- [部署说明](docs/deployment.md)
- [架构说明](docs/architecture.md)
- [公网入口说明](docs/public_portal.md)
- [提示词说明](docs/prompting.md)

## 致谢

- [nuwa-skill](https://github.com/alchaincyf/nuwa-skill)：技能蒸馏相关思路和素材参考
- [ClawTeam](https://github.com/HKUDS/ClawTeam)：多 Agent 协作模式启发来源

## License

MIT
