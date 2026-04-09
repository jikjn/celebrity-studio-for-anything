---
name: celebrity-studio-anything
description: Build and run a dynamic multi-agent framework that selects 4-8 concrete public figures for any scenario, distills skill cards, runs cross-challenge debate, and outputs consensus/disagreement/conditional recommendations. Use when user asks for celebrity-based multi-agent research, dynamic role selection, anti-fit rejection, or deep collaborative discussion.
---

# Celebrity Studio Anything Skill

Run the pipeline:

```bash
cd C:\Users\33032\Downloads\celebrity-studio-for-anything
celebrity-studio run -q "<user scenario>"
```

Offline fallback:

```bash
celebrity-studio run -q "<user scenario>" --offline
```

## Required Guarantees

- Select concrete people only, never abstract roles.
- Re-select candidates for each scenario (no fixed shortlist in main path).
- If user does not specify size, keep at least 4 agents.
- Include selected and rejected (anti-fit reasons).
- Require interaction: challenge, defense/revision, synthesis.
- Output consensus/disagreement/reservations/conditional routes.

## Main Artifacts

- `outputs/<scenario-id>/selection.json`
- `outputs/<scenario-id>/debate.json`
- `outputs/<scenario-id>/report.md`
- `data/celebrities/distilled_skills/<slug>/SKILL.md`

