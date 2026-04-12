[English](README.md) | [简体中文](README.zh-CN.md)

<div align="center">

# MindForge Studio

### 面向真实决策的开源多 Agent 讨论工作台

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

MindForge Studio 是一个面向复杂问题的多 Agent 讨论系统。
它不是单轮问答，也不是固定模板套话，而是让多个 Agent 围绕同一问题进行质疑、支持、补充和收束，最后给出更接近真实决策过程的可执行结论。

## 它能做什么

- 用自由沙龙式讨论替代僵硬工作流
- 支持配置团队人数、发言轮次、发言长度和互动风格
- 同时输出最终总结和每个 Agent 的关键观点
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

1. 解析场景问题。
2. 检索候选人物或视角。
3. 根据覆盖度、互补性和冲突生产力选择团队。
4. 蒸馏角色技能。
5. 运行多 Agent 讨论。
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
