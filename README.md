[English](README.md) | [Chinese (Simplified)](README.zh-CN.md)

<div align="center">

# MindForge Studio

### Open-source Multi-Agent Studio for Real-World Decisions

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

MindForge Studio is not a system that just grabs a few AI roles and lets them chat.
It first distills the skills that make real celebrities, creators, founders, thinkers, athletes, and historical figures valuable, then builds a scenario-specific cast whose strengths actually fit the problem.

Users provide a situation, not a vague role label.
Instead of defaulting to abstract personas like "teacher", "advisor", "director", or "analyst", the system re-selects people for each use case: Zhang Xuefeng and Yu Minhong for education planning, Lin Xi and Jay Chou for songwriting, or a different lineup for brand strategy, communication, investing, negotiation, education, sports training, creative work, or historical judgment.

Just as important, the discussion is not a stack of isolated agent opinions pasted into one report.
It runs more like a salon-style deep research session: one voice proposes a thesis, another questions the premise, another adds cases, another pushes back from a different era or field, and the group gradually converges on a more actionable conclusion.

## What Makes It Different

- Distills concrete skills from real people instead of relying on generic role templates
- Dynamically selects a cast for each scenario, so every discussion is reassembled around the actual problem
- Encourages challenge, support, counterargument, and synthesis instead of parallel monologues
- Produces a conclusion that feels closer to a real decision process, not just polished wording

## What It Does

- Distills discussion-ready skills from real people instead of applying fixed persona labels
- Dynamically selects public figures whose strengths actually match the scenario
- Runs a free-form salon-style deep discussion instead of a fixed workflow
- Supports configurable team size, speaking turns, turn length, and interaction style
- Produces both a final synthesis and per-agent takeaways instead of just stitching together parallel opinions
- Works through a local Web UI and a CLI
- Includes an optional public portal and an optional video-generation pipeline

## Example Scenarios

### 1. Cantopop x cyberpunk concept design

- Output directory: `outputs/scenario-20260408-182643/`
- Sample cast: Jan Lamb, William Chang, James Wong, Tan Dun, G.E.M., Anthony Wong
- Typical outcome: a concrete creative framework covering title direction, style ratio, imagery, and production constraints

### 2. Relationship advice from a curated team

- Output directory: `outputs/scenario-20260409-031622/`
- Sample cast: Haruki Murakami, Wang Yangming, Eileen Chang, Warren Buffett
- Typical outcome: explicit decision criteria, risk framing, and practical action steps instead of generic encouragement

### 3. Budget planning for student sports development

- Output directory: `outputs/scenario-20260409-032634/`
- Sample cast: Li Ning, Deng Yaping, Eileen Gu, Zhang Guimei, Su Bingtian, Yao Ming
- Typical outcome: a combined plan for budget allocation, training path, and academic fallback

## Quick Start

### 1. Install

```bash
python -m pip install -e .
```

### 2. Configure environment variables

Copy `.env.example` to `.env`, then set at least:

- `OPENAI_API_KEY`

Common optional settings:

- `OPENAI_BASE_URL`
- `PUBLIC_PROVIDER_API_KEY`
- `PUBLIC_PROVIDER_BASE_URL`
- `YUNWU_API_KEY`

### 3. Start the local web app

```bash
mindforge-studio-api
```

Or:

```bash
python -m celebrity_studio.api_server
```

Open:

- `http://127.0.0.1:8787/`
- `http://127.0.0.1:8787/public` for the optional public portal
- `http://127.0.0.1:8787/api/health` for a health check

### 4. Run from the CLI

```bash
python scripts/run_studio.py \
  --query "Design a Cantonese song concept that blends Chinese aesthetics with cyberpunk." \
  --team-size 6 \
  --language en \
  --provider-type codex_cli \
  --provider-model gpt-5.3-codex \
  --provider-timeout-s 300 \
  --selection-mode auto
```

Example with an explicit cast:

```bash
python scripts/run_studio.py \
  --query "Have Haruki Murakami, Wang Yangming, Eileen Chang, and Warren Buffett give relationship advice to a modern 25-year-old." \
  --team-size 4 \
  --language en \
  --provider-type codex_cli \
  --provider-model gpt-5.3-codex \
  --provider-timeout-s 300 \
  --selection-mode strict \
  --include-celebrities "Haruki Murakami,Wang Yangming,Eileen Chang,Warren Buffett"
```

> Branding note: the project is now called MindForge Studio, but the Python package name remains `celebrity_studio` for compatibility.

## Runtime Controls

You can configure these through the Web UI or runtime JSON:

- `discussion.min_turns_per_member`
- `discussion.turn_length`: `brief | standard | long | extended`
- `discussion.interaction_style`
- `selection_mode`: `auto | prefer | strict`

## How It Works

1. Parse the scenario and identify the kind of judgment it actually requires.
2. Retrieve candidate people and their distilled skill profiles.
3. Select a team based on skill fit, coverage, complementarity, and productive conflict.
4. Turn those skills into discussion-ready agent setups.
5. Run the studio discussion as a salon-style multi-agent exchange.
6. Synthesize the final result and extract agent-level takeaways.
7. Save JSON artifacts and a Markdown report.

## Output Structure

Each run writes a scenario folder under `outputs/<scenario-id>/`, including:

- `scenario.json`
- `selection.json`
- `skills.json`
- `studio.json`
- `debate.json`
- `result.json`
- `report.md`

## Documentation

- [Deployment guide](docs/deployment.md)
- [Architecture notes](docs/architecture.md)
- [Public portal guide](docs/public_portal.md)
- [Prompting notes](docs/prompting.md)

## Acknowledgements

- [nuwa-skill](https://github.com/alchaincyf/nuwa-skill) for ideas and assets around skill distillation
- [ClawTeam](https://github.com/HKUDS/ClawTeam) for collaboration-pattern inspiration

## License

MIT
