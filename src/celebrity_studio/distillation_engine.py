from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import requests

from .llm import LLMClient
from .models import (
    CelebrityCandidate,
    DecisionHeuristic,
    DistilledSkill,
    ExpressionDNA,
    MentalModel,
    ScenarioSpec,
    SkillIdentity,
    SourceAnchor,
)
from .utils import ensure_dir, read_json, slugify_name, write_json, write_text


COGNITIVE_FUNCTIONS = [
    "Visionary",
    "Realist",
    "Humanist",
    "Operator",
    "Critic",
    "Synthesizer",
    "Worldbuilder",
    "Taste Curator",
    "Systems Thinker",
    "Hook Architect",
    "Cultural Spine",
]

STYLE_PRIORS: dict[str, dict[str, Any]] = {
    "jay-chou": {
        "tone": "Hook-forward, restrained-romantic, East-West fusion",
        "rhythm": "Short memorable clauses -> image punchline -> melodic landing",
        "lexical_markers": ["hook", "留白", "旋律骨架", "质感", "记忆点"],
        "taboo_phrasing": ["full technical jargon without melody", "flat plain-language chorus"],
        "challenge_style": "Challenge weak hooks and over-stacked arrangement before agreeing.",
    },
    "james-wong": {
        "tone": "Cultural spine, rhetorical weight, Cantonese-classical tension",
        "rhythm": "Concept framing -> diction precision -> moral/poetic turn",
        "lexical_markers": ["气口", "词骨", "文白交错", "粤语张力", "传统语汇"],
        "taboo_phrasing": ["empty pseudo-classical wording", "surface-level chinese-style labels"],
        "challenge_style": "Challenge cultural shallowness and weak linguistic craftsmanship.",
    },
    "wong-kar-wai": {
        "tone": "Cinematic, urban melancholic, sensory-driven",
        "rhythm": "Scene anchor -> emotional drift -> motif recurrence",
        "lexical_markers": ["霓虹", "旧城", "雨夜", "错位", "都市孤独"],
        "taboo_phrasing": ["purely technical story without emotion", "generic city description"],
        "challenge_style": "Challenge emotionless worldbuilding and atmosphere inconsistency.",
    },
    "lin-xi": {
        "tone": "Symbolic compression, emotionally precise, lyrical",
        "rhythm": "Concrete image -> semantic inversion -> lingering aftertaste",
        "lexical_markers": ["意象压缩", "双关", "情绪锚点", "句核", "复唱"],
        "taboo_phrasing": ["literal explanatory lyrics", "overwritten abstract slogans"],
        "challenge_style": "Challenge lyrical looseness and weak semantic density.",
    },
    "mamoru-oshii": {
        "tone": "Cold philosophical systems critique",
        "rhythm": "Premise -> contradiction -> existential consequence",
        "lexical_markers": ["身份", "记忆", "系统", "异化", "伦理冲突"],
        "taboo_phrasing": ["pure neon aesthetics without conflict", "sentimental resolution without stakes"],
        "challenge_style": "Challenge shallow cyberpunk aesthetics lacking core conflict.",
    },
}


def _default_expression(candidate: CelebrityCandidate, spec: ScenarioSpec, slug: str) -> ExpressionDNA:
    prior = STYLE_PRIORS.get(slug)
    if prior is not None:
        return ExpressionDNA(
            tone=str(prior["tone"]),
            rhythm=str(prior["rhythm"]),
            lexical_markers=[str(x) for x in prior.get("lexical_markers", [])],
            taboo_phrasing=[str(x) for x in prior.get("taboo_phrasing", [])],
            challenge_style=str(prior["challenge_style"]),
        )

    text = f"{candidate.description} {' '.join(candidate.domains)} {spec.raw_user_query}".lower()
    if any(token in text for token in ("music", "song", "cantopop", "composer", "lyrics")):
        return ExpressionDNA(
            tone="Melodic-pragmatic, user-ear first",
            rhythm="Hook hypothesis -> arrangement constraint -> revision",
            lexical_markers=["hook", "phrase", "cadence", "singability", "texture"],
            taboo_phrasing=["concept pile with no chorus", "ornament-only chinese-style tags"],
            challenge_style="Challenge singability and memory retention risks first.",
        )
    if any(token in text for token in ("film", "cinema", "world", "atmosphere", "cyberpunk")):
        return ExpressionDNA(
            tone="Atmospheric and conflict-aware",
            rhythm="Scene setup -> contradiction -> narrative pressure",
            lexical_markers=["scene", "mood", "conflict", "motif", "worldbuilding"],
            taboo_phrasing=["empty style labels", "conflict-free worldbuilding"],
            challenge_style="Challenge mood-world mismatch and weak narrative conflict.",
        )
    return ExpressionDNA(
        tone="Direct and structured",
        rhythm="Claim -> evidence -> boundary",
        lexical_markers=["fit", "tradeoff", "constraint", "evidence", "execution"],
        taboo_phrasing=["absolute certainty without evidence", "fame-based authority only"],
        challenge_style="Target assumptions, feasibility, and user-fit before agreeing.",
    )


def _needs_style_refresh(skill: DistilledSkill, slug: str) -> bool:
    if slug not in STYLE_PRIORS:
        return False
    exp = skill.expression_dna
    return (
        exp.tone.strip().lower() == "direct and structured"
        and exp.rhythm.strip().lower() == "claim -> evidence -> boundary"
    )


def _wiki_summary_from_url(url: str) -> str:
    try:
        title = unquote(url.rsplit("/", 1)[-1])
        endpoint = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
        response = requests.get(endpoint, timeout=15)
        response.raise_for_status()
        payload = response.json()
        return str(payload.get("extract", ""))
    except Exception:
        return ""


def _collect_source_anchors(candidate: CelebrityCandidate) -> list[SourceAnchor]:
    anchors: list[SourceAnchor] = []
    if candidate.wikidata_id:
        anchors.append(
            SourceAnchor(
                title=f"Wikidata {candidate.wikidata_id}",
                url=f"https://www.wikidata.org/wiki/{candidate.wikidata_id}",
                source_type="wiki",
                note="Entity metadata and public graph references.",
            )
        )
    if candidate.wikipedia_url:
        summary = _wiki_summary_from_url(candidate.wikipedia_url)
        anchors.append(
            SourceAnchor(
                title=f"Wikipedia: {candidate.name}",
                url=candidate.wikipedia_url,
                source_type="wiki",
                note=summary[:280] if summary else "Public summary page.",
            )
        )
    return anchors


def _default_role(candidate: CelebrityCandidate, spec: ScenarioSpec) -> str:
    text = f"{candidate.description} {' '.join(candidate.domains)}".lower()
    if any(x in text for x in ("cantopop", "song", "melody", "composer", "music")):
        return "Hook Architect"
    if any(x in text for x in ("chinese", "poetry", "cantonese", "culture", "lyric")):
        return "Cultural Spine"
    if any(x in text for x in ("cyberpunk", "fiction", "world", "atmosphere", "cinema")):
        return "Worldbuilder"
    if any(x in text for x in ("teacher", "educat", "professor", "writer")):
        return "Humanist"
    if any(x in text for x in ("business", "entrepreneur", "executive", "ceo")):
        return "Operator"
    if any(x in text for x in ("scientist", "physicist", "mathematician")):
        return "Critic"
    if any(x in text for x in ("artist", "musician", "director", "designer")):
        return "Taste Curator"
    if "education" in spec.domain_tags:
        return "Humanist"
    return "Systems Thinker"


def _normalize_cognitive_function(role: str, candidate: CelebrityCandidate, spec: ScenarioSpec) -> str:
    cleaned = role.strip()
    if not cleaned:
        return _default_role(candidate, spec)
    lower = cleaned.lower()
    if "strategist" in lower:
        return "Systems Thinker"
    if "educator" in lower:
        return "Humanist"
    if "taste builder" in lower:
        return "Taste Curator"
    if "first-principles" in lower:
        return "Critic"
    for value in COGNITIVE_FUNCTIONS:
        if value.lower() in lower:
            return value
    # hard guard against job-title collapse
    if any(token in lower for token in ("lead", "manager", "director of", "owner", "executor", "coordinator")):
        return _default_role(candidate, spec)
    return cleaned


def _heuristic_skill(candidate: CelebrityCandidate, spec: ScenarioSpec, anchors: list[SourceAnchor]) -> DistilledSkill:
    slug = slugify_name(candidate.name)
    domain_hint = candidate.domains[0] if candidate.domains else "general decision"
    mental_models = [
        MentalModel(
            name=f"{candidate.name}: Outcome-Back Reasoning",
            one_liner="Start from outcome constraints and back-chain feasible choices.",
            evidence=[candidate.description or f"Public profile in {domain_hint}."],
            application="Use when scenario requires constrained decisions with tradeoffs.",
            limitation="Can underweight emotional or long-horizon human factors if overused.",
        ),
        MentalModel(
            name=f"{candidate.name}: Competitive Positioning Lens",
            one_liner="Judge options by relative edge instead of absolute preference.",
            evidence=[f"Domains: {', '.join(candidate.domains) or 'general'}"],
            application="Use when user must choose among high-competition options.",
            limitation="May be too harsh for early-stage exploratory learning goals.",
        ),
        MentalModel(
            name=f"{candidate.name}: Risk-Adjusted Pragmatism",
            one_liner="Prefer robust moves with asymmetric upside and controlled downside.",
            evidence=["Nuwa-inspired distilled heuristic pattern with anti-fit guardrails."],
            application="Use when uncertainty and resource constraints both matter.",
            limitation="May miss moonshot opportunities requiring concentrated bets.",
        ),
    ]
    heuristics = [
        DecisionHeuristic(
            name="Constraint First",
            rule="List non-negotiable constraints before proposing solutions.",
            when_to_use="Whenever budget, timeline, policy, or capability limits are explicit.",
            counter_signal="Do not use as sole filter when breakthrough innovation is the goal.",
        ),
        DecisionHeuristic(
            name="Anti-Fit Filter",
            rule="Reject options with thematic mismatch even if they are famous or fashionable.",
            when_to_use="Always use during candidate selection and recommendation synthesis.",
            counter_signal="Relax only when deliberately adding contrarian stress tests.",
        ),
        DecisionHeuristic(
            name="Evidence over Vibe",
            rule="Require an observable anchor for each major claim.",
            when_to_use="Use during free-salon exploration and convergence synthesis.",
            counter_signal="Allow soft reasoning only in explicitly creative tasks.",
        ),
        DecisionHeuristic(
            name="Conditional Advice",
            rule="Convert each recommendation into 'works when / fails when' statements.",
            when_to_use="In final synthesis for user-facing decision output.",
            counter_signal="Skip only if user asks for pure brainstorming.",
        ),
        DecisionHeuristic(
            name="Iterative Alignment",
            rule="When resonance reveals conflict, update assumptions instead of repeating fixed stances.",
            when_to_use="In any Open Studio Field round where thread quality stalls.",
            counter_signal="Not needed when the current thread is still producing concrete insight.",
        ),
    ]
    expression = _default_expression(candidate, spec, slug)
    return DistilledSkill(
        slug=slug,
        identity=SkillIdentity(
            name=candidate.name,
            era=candidate.era,
            domains=candidate.domains or [domain_hint],
            confidence=min(0.95, 0.45 + candidate.evidence_availability * 0.5),
        ),
        mental_models=mental_models,
        decision_heuristics=heuristics,
        expression_dna=expression,
        values_and_taboo=[
            "Prioritize user-fit over ideological purity.",
            "Avoid abstract posturing without operational implications.",
        ],
        blindspots=[
            "Public materials may overrepresent polished narratives.",
            "Historical context can be misapplied to modern institutional constraints.",
        ],
        uncertainty_policy="Mark low-confidence claims explicitly and request more context.",
        honest_boundaries=[
            "This is a distilled cognitive profile, not the person.",
            "Cannot replace domain-specific legal/medical/regulated advice.",
        ],
        best_fit_scenarios=[
            f"Scenario requiring {domain_hint} judgment under constraints.",
            "High-stakes decisions where competing routes need stress-testing.",
        ],
        worst_fit_scenarios=[
            "Tasks needing private data unavailable in public records.",
            "Purely technical tasks outside this person's documented domain footprint.",
        ],
        collaboration_role=_default_role(candidate, spec),
        source_anchors=anchors,
    )


def _llm_skill(candidate: CelebrityCandidate, spec: ScenarioSpec, anchors: list[SourceAnchor], llm: LLMClient) -> DistilledSkill:
    role_constraint = ", ".join(COGNITIVE_FUNCTIONS)
    slug = slugify_name(candidate.name)
    style_anchor = STYLE_PRIORS.get(slug)
    prompt = (
        "You are a Nuwa-style distillation engine. "
        "Extract cognitive operating system with public stylistic signature, not private-roleplay cosplay.\n"
        "Return JSON only with keys:\n"
        "mental_models (3-7), decision_heuristics (5-10), expression_dna, "
        "values_and_taboo, blindspots, uncertainty_policy, honest_boundaries, "
        "best_fit_scenarios, worst_fit_scenarios, collaboration_role.\n"
        "Each mental model item: {name, one_liner, evidence, application, limitation}.\n"
        "Each decision heuristic item: {name, rule, when_to_use, counter_signal}.\n"
        "expression_dna: {tone, rhythm, lexical_markers, taboo_phrasing, challenge_style}.\n"
        "expression_dna should preserve recognizable public voice tendencies "
        "(cadence, lexical motifs, imagery pressure), while staying safe and bounded.\n"
        f"collaboration_role must be a cognitive function (not a job title), preferably from: {role_constraint}.\n"
        f"style_anchor={style_anchor}\n"
        f"scenario={spec.model_dump()}\n"
        f"candidate={candidate.model_dump()}\n"
        f"anchors={[a.model_dump() for a in anchors]}"
    )
    parsed = llm.complete_json(
        system_prompt="Distill public figures into robust skill cards for multi-agent collaboration.",
        user_prompt=prompt,
    )
    raw_expression = parsed.get("expression_dna", {})
    try:
        expression = ExpressionDNA(**raw_expression)
    except Exception:
        expression = _default_expression(candidate, spec, slug)
    if not expression.lexical_markers:
        expression.lexical_markers = _default_expression(candidate, spec, slug).lexical_markers

    return DistilledSkill(
        slug=slug,
        identity=SkillIdentity(
            name=candidate.name,
            era=candidate.era,
            domains=candidate.domains or spec.domain_tags,
            confidence=min(0.95, 0.55 + candidate.evidence_availability * 0.4),
        ),
        mental_models=[MentalModel(**item) for item in parsed.get("mental_models", [])][:7],
        decision_heuristics=[DecisionHeuristic(**item) for item in parsed.get("decision_heuristics", [])][:10],
        expression_dna=expression,
        values_and_taboo=[str(x) for x in parsed.get("values_and_taboo", [])],
        blindspots=[str(x) for x in parsed.get("blindspots", [])],
        uncertainty_policy=str(parsed.get("uncertainty_policy", "Explicitly surface uncertainty.")),
        honest_boundaries=[str(x) for x in parsed.get("honest_boundaries", [])],
        best_fit_scenarios=[str(x) for x in parsed.get("best_fit_scenarios", [])],
        worst_fit_scenarios=[str(x) for x in parsed.get("worst_fit_scenarios", [])],
        collaboration_role=_normalize_cognitive_function(
            str(parsed.get("collaboration_role", _default_role(candidate, spec))),
            candidate,
            spec,
        ),
        source_anchors=anchors,
    )


def _skill_markdown(skill: DistilledSkill) -> str:
    mm_lines = "\n".join(
        f"### {idx}. {model.name}\n"
        f"- One-liner: {model.one_liner}\n"
        f"- Application: {model.application}\n"
        f"- Limitation: {model.limitation}\n"
        f"- Evidence: {', '.join(model.evidence)}"
        for idx, model in enumerate(skill.mental_models, start=1)
    )
    heuristic_lines = "\n".join(
        f"{idx}. **{heur.name}**\n"
        f"- Rule: {heur.rule}\n"
        f"- When: {heur.when_to_use}\n"
        f"- Counter-signal: {heur.counter_signal}"
        for idx, heur in enumerate(skill.decision_heuristics, start=1)
    )
    source_lines = "\n".join(f"- [{anchor.title}]({anchor.url}) ({anchor.source_type})" for anchor in skill.source_anchors)
    return (
        f"# {skill.identity.name} Skill Card\n\n"
        "## Identity\n"
        f"- Era: {skill.identity.era}\n"
        f"- Domains: {', '.join(skill.identity.domains)}\n"
        f"- Confidence: {skill.identity.confidence:.2f}\n\n"
        "## Core Mental Models\n"
        f"{mm_lines}\n\n"
        "## Decision Heuristics\n"
        f"{heuristic_lines}\n\n"
        "## Expression DNA\n"
        f"- Tone: {skill.expression_dna.tone}\n"
        f"- Rhythm: {skill.expression_dna.rhythm}\n"
        f"- Lexical markers: {', '.join(skill.expression_dna.lexical_markers)}\n"
        f"- Taboo phrasing: {', '.join(skill.expression_dna.taboo_phrasing)}\n"
        f"- Challenge style: {skill.expression_dna.challenge_style}\n\n"
        "## Values / Taboo\n"
        + "\n".join(f"- {item}" for item in skill.values_and_taboo)
        + "\n\n## Blindspots\n"
        + "\n".join(f"- {item}" for item in skill.blindspots)
        + "\n\n## Honest Boundaries\n"
        + "\n".join(f"- {item}" for item in skill.honest_boundaries)
        + "\n\n## Best-fit Scenarios\n"
        + "\n".join(f"- {item}" for item in skill.best_fit_scenarios)
        + "\n\n## Worst-fit Scenarios\n"
        + "\n".join(f"- {item}" for item in skill.worst_fit_scenarios)
        + "\n\n## Collaboration Role\n"
        + f"- {skill.collaboration_role}\n\n"
        + "## Source Anchors\n"
        + source_lines
        + "\n"
    )


def _validation_payload(skill: DistilledSkill) -> dict[str, Any]:
    return {
        "mental_model_count": len(skill.mental_models),
        "heuristic_count": len(skill.decision_heuristics),
        "has_boundaries": bool(skill.honest_boundaries),
        "has_best_and_worst_fit": bool(skill.best_fit_scenarios and skill.worst_fit_scenarios),
        "has_collaboration_role": bool(skill.collaboration_role),
        "passes_minimum_gate": len(skill.mental_models) >= 3 and len(skill.decision_heuristics) >= 5,
    }


def _persist_skill(skill_dir: Path, skill: DistilledSkill) -> None:
    ensure_dir(skill_dir)
    write_json(skill_dir / "profile.json", skill.model_dump())
    write_json(skill_dir / "sources.json", {"source_anchors": [item.model_dump() for item in skill.source_anchors]})
    write_json(skill_dir / "validation.json", _validation_payload(skill))
    write_text(skill_dir / "SKILL.md", _skill_markdown(skill))


def _load_cached_skill(skill_dir: Path) -> DistilledSkill | None:
    profile_path = skill_dir / "profile.json"
    if not profile_path.exists():
        return None
    payload = read_json(profile_path)
    return DistilledSkill(**payload)


def _distill_one_candidate(
    idx: int,
    candidate: CelebrityCandidate,
    spec: ScenarioSpec,
    llm: LLMClient | None,
    root: Path,
    realtime: bool,
) -> tuple[int, DistilledSkill]:
    slug = slugify_name(candidate.name)
    skill_dir = root / slug
    cached = _load_cached_skill(skill_dir)
    if cached is not None and not realtime:
        if _needs_style_refresh(cached, slug):
            anchors = _collect_source_anchors(candidate)
            refreshed = _heuristic_skill(candidate, spec, anchors)
            refreshed.collaboration_role = _normalize_cognitive_function(refreshed.collaboration_role, candidate, spec)
            _persist_skill(skill_dir, refreshed)
            return idx, refreshed
        cached.collaboration_role = _normalize_cognitive_function(cached.collaboration_role, candidate, spec)
        return idx, cached

    # Fast path for non-realtime runs: no LLM call, deterministic heuristic distillation.
    if not realtime:
        anchors = _collect_source_anchors(candidate)
        skill = _heuristic_skill(candidate, spec, anchors)
        skill.collaboration_role = _normalize_cognitive_function(skill.collaboration_role, candidate, spec)
        _persist_skill(skill_dir, skill)
        return idx, skill

    anchors = _collect_source_anchors(candidate)
    if llm is None:
        skill = _heuristic_skill(candidate, spec, anchors)
    else:
        try:
            skill = _llm_skill(candidate, spec, anchors, llm)
        except Exception:
            skill = cached if cached is not None else _heuristic_skill(candidate, spec, anchors)

    skill.collaboration_role = _normalize_cognitive_function(skill.collaboration_role, candidate, spec)
    _persist_skill(skill_dir, skill)
    return idx, skill


def distill_selected_candidates(
    spec: ScenarioSpec,
    selected: list[CelebrityCandidate],
    llm: LLMClient | None,
    data_dir: Path,
    realtime: bool = True,
    require_online: bool = False,
) -> list[DistilledSkill]:
    if require_online and llm is None:
        raise RuntimeError("Realtime distillation requires an online LLM provider.")
    root = data_dir / "celebrities" / "distilled_skills"
    ensure_dir(root)
    if not selected:
        return []

    max_workers = min(8, max(1, len(selected)))
    by_index: dict[int, DistilledSkill] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_distill_one_candidate, idx, candidate, spec, llm, root, realtime)
            for idx, candidate in enumerate(selected)
        ]
        for future in as_completed(futures):
            idx, skill = future.result()
            by_index[idx] = skill

    return [by_index[idx] for idx in range(len(selected))]
