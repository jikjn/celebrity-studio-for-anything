# Product Spec

## Product

- Name: MindForge Studio
- Goal: For any scenario, dynamically select 4-8 concrete public figures, run real multi-agent interaction, and output deeper actionable guidance than single-agent responses.

## Input

- Natural-language scenario from user
- Optional desired team size
- Optional include/exclude celebrity lists
- Selection mode: auto / prefer / strict
- Runtime provider config (multi-API)

## Output

- ScenarioSpec
- Selected + Rejected candidates (with anti-fit reasons)
- Distilled skill artifacts
- Multi-round interaction trace
- Consensus / disagreement / reservations
- Conditional recommendation routes
- Interaction/resonance graph data

## Hard Rules

- No abstract roles
- Concrete public figures only
- No fixed shortlist in main logic
- Default team size >= 4 if not provided
- Selector objective is not top-score-only; it optimizes:
  - thematic fit
  - cognitive coverage
  - complementarity
  - conflict productivity
  - anti-popularity bias (when fit is adequate)
- Real interaction required:
  - challenge
  - defense/revision/concede
  - synthesis with traceability
