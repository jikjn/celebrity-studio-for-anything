# Architecture

## Runtime Architecture

1. Scenario Parser  
   Query -> `ScenarioSpec`

2. Dynamic Candidate Retrieval  
   Wikidata + Wikipedia dynamic retrieval (no fixed celebrity pool)

3. Candidate Ranking  
   fit / anti-fit / cognitive coverage / complementarity / conflict productivity / anti-popularity bias
   + optional include/exclude/strict constraints -> selected + rejected

4. Realtime Distillation  
   Selected celebrities -> `DistilledSkill` artifacts (`SKILL.md`, profile, sources, validation)
   (parallelized per candidate for speed)

5. Studio Composition  
   Build leader + members + optional reserve members

6. Open Studio Field Collaboration  
   Independent `AgentSession` per member  
   Independent leader session  
   Stage-A..E with free-salon rounds, center surfacing, and natural convergence

7. Synthesis + Formatting  
   Consensus / disagreement / reservations / conditional recommendations

8. Delivery Layer  
   CLI + FastAPI + Web UI (interaction graph + timeline)

## Performance Notes
- Candidate retrieval uses bounded parallel requests (search + entity detail fetch).
- Distillation runs in parallel per selected candidate.
- Open-room and free-salon turns run in parallel where dependencies allow.

## Data Artifacts

- `outputs/<scenario-id>/scenario.json`
- `outputs/<scenario-id>/selection.json`
- `outputs/<scenario-id>/skills.json`
- `outputs/<scenario-id>/studio.json`
- `outputs/<scenario-id>/debate.json`
- `outputs/<scenario-id>/report.md`
- `outputs/<scenario-id>/result.json`
