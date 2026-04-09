from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Literal

from .llm import LLMClient
from .models import CelebrityCandidate, ScenarioSpec, SelectionResult


ANTI_FIT_HINTS: dict[str, set[str]] = {
    "education": {"warlord", "dictator"},
    "branding": {"theologian", "saint"},
    "product": {"saint", "theologian"},
}

DOMAIN_RELEVANCE_HINTS: dict[str, set[str]] = {
    "music": {"music", "musician", "singer", "composer", "songwriter", "lyricist", "producer", "melody", "cantopop"},
    "culture_fusion": {"culture", "cross-cultural", "chinese", "cantonese", "fusion", "worldbuilding", "film", "aesthetic"},
    "product": {"product", "startup", "design", "engineering", "operator", "founder", "ship"},
    "branding": {"brand", "marketing", "narrative", "taste", "positioning", "media"},
    "education": {"education", "teacher", "professor", "pedagogy", "learning", "curriculum"},
    "business": {"business", "investor", "operator", "strategy", "management", "entrepreneur"},
    "science": {"scientist", "research", "physics", "biology", "mathematics", "experiment"},
}

DOMAIN_MISMATCH_HINTS: dict[str, set[str]] = {
    "music": {"photographer", "photography", "photojournalist", "astronaut", "military"},
    "science": {"socialite", "influencer"},
    "product": {"saint", "theologian"},
    "education": {"warlord", "dictator"},
}

# Frequent globally-famous names; used for mild anti-popularity bias only when fit is already adequate.
POPULARITY_PRIORS: dict[str, float] = {
    "steve jobs": 0.95,
    "jay chou": 0.92,
    "confucius": 0.95,
    "donald trump": 0.97,
    "charlie munger": 0.90,
    "warren buffett": 0.95,
    "jack ma": 0.94,
    "elon musk": 0.98,
}

COGNITIVE_TAG_HINTS: dict[str, set[str]] = {
    "visionary": {"vision", "future", "creative", "artist", "composer", "director", "design"},
    "realist": {"operator", "business", "execution", "pragmatic", "management", "feasibility"},
    "humanist": {"education", "culture", "ethics", "language", "lyric", "psychology"},
    "critic": {"risk", "critic", "skeptic", "analysis", "first-principles", "scientist"},
    "systems_thinker": {"systems", "architecture", "policy", "strategy", "governance"},
    "taste_curator": {"aesthetic", "cinema", "style", "taste", "brand", "narrative"},
    "worldbuilder": {"world", "fiction", "cyberpunk", "myth", "story", "atmosphere"},
    "operator": {"producer", "ceo", "founder", "industrial", "workflow", "ship"},
    "hook_architect": {"song", "melody", "cantopop", "music", "chorus", "hook"},
    "cultural_spine": {"tradition", "chinese", "classical", "poetry", "cantonese", "heritage"},
}

SCENARIO_COGNITIVE_AXES: dict[str, list[str]] = {
    "music": ["hook_architect", "taste_curator", "operator"],
    "culture_fusion": ["cultural_spine", "worldbuilder", "systems_thinker"],
    "product": ["visionary", "realist", "critic", "operator"],
    "branding": ["taste_curator", "visionary", "humanist"],
    "education": ["humanist", "realist", "critic"],
    "business": ["realist", "systems_thinker", "operator", "critic"],
    "science": ["critic", "systems_thinker", "realist"],
}

USER_INCLUDE_PROFILES: dict[str, tuple[str, list[str]]] = {
    "jay chou": (
        "Taiwanese singer-songwriter and producer known for East-West fusion and hook architecture.",
        ["music", "songwriting", "arrangement", "hook"],
    ),
    "james wong": (
        "Hong Kong lyricist-composer known for cultural spine and Cantonese expression.",
        ["cantopop", "lyrics", "culture", "composition"],
    ),
    "wong kar-wai": (
        "Hong Kong film auteur known for neon-urban atmosphere and emotional worldbuilding.",
        ["worldbuilding", "atmosphere", "cinematic language", "taste"],
    ),
    "lin xi": (
        "Cantonese lyricist known for symbolic compression and emotional precision.",
        ["lyrics", "cantonese", "symbolic writing", "humanist framing"],
    ),
    "mamoru oshii": (
        "Director and writer known for cyberpunk ontology and identity conflict design.",
        ["cyberpunk", "worldbuilding", "identity conflict", "systems thinking"],
    ),
    "confucius": (
        "Ancient Chinese philosopher emphasizing ethics, education, and social order.",
        ["ethics", "education", "humanist", "civilization lens"],
    ),
    "charlie munger": (
        "Investor-thinker known for multidisciplinary mental models and critical reasoning.",
        ["critic", "decision making", "risk", "mental models"],
    ),
}

NAME_ALIAS_GROUPS: dict[str, set[str]] = {
    "jay chou": {"jay chou", "zhou jielun", "jielun zhou", "周杰伦", "周杰倫", "周董"},
    "james wong": {"james wong", "james wong jim", "wong jim", "黄霑", "黃霑", "黄沾"},
    "wong kar-wai": {"wong kar-wai", "wong kar wai", "王家卫", "王家衛"},
    "lin xi": {"lin xi", "linxi", "林夕", "albert leung"},
    "mamoru oshii": {"mamoru oshii", "oshii mamoru", "押井守"},
    "confucius": {"confucius", "kongzi", "kong fuzi", "孔子"},
    "charlie munger": {"charlie munger", "查理芒格", "查理·芒格", "查理 芒格"},
}


def _tokenize(value: str) -> set[str]:
    raw_tokens = re.findall(r"[a-zA-Z]{3,}|[\u4e00-\u9fff]{1,4}", value.lower())
    return {token for token in raw_tokens if token.strip()}


def _normalize_name(value: str) -> str:
    lowered = value.strip().lower()
    lowered = lowered.replace("·", " ").replace("-", " ")
    lowered = re.sub(r"[()（）\[\]{}'\"`]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _build_alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for canonical, aliases in NAME_ALIAS_GROUPS.items():
        canonical_norm = _normalize_name(canonical)
        index[canonical_norm] = canonical_norm
        for alias in aliases:
            alias_norm = _normalize_name(alias)
            if alias_norm:
                index[alias_norm] = canonical_norm
    return index


NAME_ALIAS_TO_CANONICAL: dict[str, str] = _build_alias_index()


def _canonical_name(value: str) -> str:
    normalized = _normalize_name(value)
    return NAME_ALIAS_TO_CANONICAL.get(normalized, normalized)


NORMALIZED_USER_INCLUDE_PROFILES: dict[str, tuple[str, list[str]]] = {
    _normalize_name(name): profile for name, profile in USER_INCLUDE_PROFILES.items()
}


def _scenario_axes(spec: ScenarioSpec) -> list[str]:
    axes: list[str] = []
    for domain in spec.domain_tags:
        axes.extend(SCENARIO_COGNITIVE_AXES.get(domain, []))
    if not axes:
        axes = ["visionary", "realist", "critic", "systems_thinker"]
    dedup: list[str] = []
    seen: set[str] = set()
    for axis in axes:
        if axis not in seen:
            seen.add(axis)
            dedup.append(axis)
    return dedup


def _domain_alignment_score(spec: ScenarioSpec, candidate: CelebrityCandidate) -> tuple[float, float]:
    if not spec.domain_tags:
        return 0.0, 0.0

    lowered_text = " ".join([candidate.name, candidate.description, *candidate.domains]).lower()
    domains = [domain.lower() for domain in spec.domain_tags]
    matched = 0
    mismatch_hits = 0

    for domain in domains:
        hints = DOMAIN_RELEVANCE_HINTS.get(domain, {domain})
        if any(token in lowered_text for token in hints):
            matched += 1
        mismatch_tokens = DOMAIN_MISMATCH_HINTS.get(domain, set())
        if mismatch_tokens and any(token in lowered_text for token in mismatch_tokens):
            mismatch_hits += 1

    match_ratio = matched / max(1, len(domains))
    penalty = 0.0
    if matched == 0:
        penalty += 0.16
    penalty += min(0.45, mismatch_hits * 0.14)
    return match_ratio, penalty


def _candidate_primary_aspect(spec: ScenarioSpec, candidate: CelebrityCandidate) -> str:
    tags = _candidate_cognitive_tags(candidate)
    scenario_axes = _scenario_axes(spec)
    for axis in scenario_axes:
        if axis in tags:
            return axis
    if tags:
        return sorted(tags)[0]
    return "realist"


def _inject_llm_retrieved_candidates(
    spec: ScenarioSpec,
    candidates: list[CelebrityCandidate],
    llm: LLMClient | None,
    include_celebrities: list[str],
    min_required: int,
    max_new: int = 8,
) -> tuple[list[CelebrityCandidate], list[str]]:
    if llm is None or max_new <= 0:
        return candidates, []

    target_count = max(4, int(min_required))
    include_hint = [name.strip() for name in include_celebrities if name.strip()]
    include_note = ", ".join(include_hint) if include_hint else "(none)"
    try:
        parsed = llm.complete_json(
            system_prompt=(
                "You are a public-figure retrieval engine for a multi-agent studio. "
                "Return only concrete people, not abstract roles."
            ),
            user_prompt=(
                "Task: Please retrieve public figures relevant to the theme.\n"
                f"Theme: {spec.raw_user_query}\n"
                f"Domain tags: {spec.domain_tags}\n"
                f"Task types: {spec.task_types}\n"
                f"Language: {spec.language}\n"
                f"User required figures: {include_note}\n"
                f"Selection rule: diversify fields whenever possible. If user did not specify, return at least {target_count} people.\n"
                "Return JSON with key candidates. Each item: "
                "{\"name\":\"\", \"description\":\"\", \"domains\":[], \"aspect\":\"\", \"reason\":\"\", \"field\":\"\"}. "
                "Prefer 8-12 candidates when available."
            ),
        )
    except Exception:
        return candidates, []

    existing = {_canonical_name(candidate.name) for candidate in candidates}
    out = list(candidates)
    additions = 0
    for item in parsed.get("candidates", []):
        name = str(item.get("name", "")).strip()
        canonical = _canonical_name(name)
        if not name or not canonical or canonical in existing:
            continue
        domains = [str(x).strip() for x in item.get("domains", []) if str(x).strip()]
        aspect = str(item.get("aspect", "")).strip()
        if aspect and aspect.lower() not in {domain.lower() for domain in domains}:
            domains = [aspect, *domains]
        description = str(item.get("description", "")).strip()
        reason = str(item.get("reason", "")).strip()
        out.append(
            CelebrityCandidate(
                name=name,
                description=description or reason or "LLM-retrieved figure for thematic relevance.",
                domains=domains[:6] or ["llm-retrieved"],
                verified_human=True,
                era="modern",
                fit_reasons=["LLM API retrieval suggested this figure for this scenario."],
                evidence_availability=0.36,
                distillability_score=0.42,
                controversy_risk=0.32,
            )
        )
        existing.add(canonical)
        additions += 1
        if additions >= max_new:
            break

    rationale: list[str] = []
    if additions:
        rationale.append(f"LLM retrieval injected {additions} additional scenario-relevant candidate(s).")
    return out, rationale


def _llm_rank_guidance(
    spec: ScenarioSpec,
    candidates: list[CelebrityCandidate],
    llm: LLMClient | None,
) -> tuple[dict[str, float], dict[str, str], list[str]]:
    if llm is None or not candidates:
        return {}, {}, []
    compact = [
        {
            "name": candidate.name,
            "description": candidate.description[:180],
            "domains": candidate.domains[:4],
        }
        for candidate in candidates[:40]
    ]
    try:
        parsed = llm.complete_json(
            system_prompt=(
                "You are a selector for scenario-fit public figures. "
                "Pick candidates from the provided list only."
            ),
            user_prompt=(
                f"scenario={spec.raw_user_query}\n"
                f"domain_tags={spec.domain_tags}\n"
                f"task_types={spec.task_types}\n"
                f"candidate_pool={compact}\n"
                "Return JSON with key picks. Each item: "
                "{\"name\":\"\", \"score\":0.0, \"aspect\":\"\", \"reason\":\"\"}. "
                "Pick up to 12 candidates."
            ),
        )
    except Exception:
        return {}, {}, []

    bonus: dict[str, float] = {}
    aspect_by_name: dict[str, str] = {}
    rationale: list[str] = []
    for item in parsed.get("picks", []):
        name = str(item.get("name", "")).strip()
        canonical = _canonical_name(name)
        if not canonical:
            continue
        try:
            score = float(item.get("score", 0.0))
        except Exception:
            score = 0.0
        bonus[canonical] = max(0.0, min(0.18, score * 0.18))
        aspect = str(item.get("aspect", "")).strip()
        if aspect:
            aspect_by_name[canonical] = aspect
        reason = str(item.get("reason", "")).strip()
        if reason:
            rationale.append(f"{name}: {reason}")
    return bonus, aspect_by_name, rationale[:8]


def _ensure_aspect_diversity(
    spec: ScenarioSpec,
    selected: list[CelebrityCandidate],
    ranked_pool: list[CelebrityCandidate],
    target_size: int,
    min_aspects: int,
    llm_aspect_hints: dict[str, str],
) -> list[CelebrityCandidate]:
    if not selected or min_aspects <= 1:
        return selected
    min_viable_score = 0.25

    ordered = list(selected)
    selected_keys = {_canonical_name(candidate.name) for candidate in ordered}

    def aspect_of(candidate: CelebrityCandidate) -> str:
        canonical = _canonical_name(candidate.name)
        hinted = llm_aspect_hints.get(canonical, "").strip()
        if hinted:
            return hinted.lower()
        return _candidate_primary_aspect(spec, candidate)

    def aspect_counts(items: list[CelebrityCandidate]) -> Counter[str]:
        return Counter(aspect_of(item) for item in items)

    while True:
        counts = aspect_counts(ordered)
        if len(counts) >= min_aspects:
            break
        candidate_to_add: CelebrityCandidate | None = None
        for candidate in ranked_pool:
            canonical = _canonical_name(candidate.name)
            if canonical in selected_keys:
                continue
            if candidate.final_score < min_viable_score:
                continue
            if aspect_of(candidate) not in counts:
                candidate_to_add = candidate
                break
        if candidate_to_add is None:
            break

        if len(ordered) < target_size:
            ordered.append(candidate_to_add)
            selected_keys.add(_canonical_name(candidate_to_add.name))
            continue

        replace_index = -1
        replace_score = 10.0
        for idx, item in enumerate(ordered):
            current_aspect = aspect_of(item)
            if counts[current_aspect] <= 1:
                continue
            if item.final_score < replace_score:
                replace_index = idx
                replace_score = item.final_score
        if replace_index < 0:
            break
        if candidate_to_add.final_score + 0.08 < replace_score:
            break

        removed = ordered[replace_index]
        selected_keys.remove(_canonical_name(removed.name))
        ordered[replace_index] = candidate_to_add
        selected_keys.add(_canonical_name(candidate_to_add.name))

    return ordered


def _candidate_cognitive_tags(candidate: CelebrityCandidate) -> set[str]:
    text = " ".join([candidate.name, candidate.description, *candidate.domains]).lower()
    tags: set[str] = set()
    for tag, hints in COGNITIVE_TAG_HINTS.items():
        if any(hint in text for hint in hints):
            tags.add(tag)
    if not tags:
        tags = {"realist"}
    return tags


def _popularity_proxy(candidate: CelebrityCandidate) -> float:
    base = max(0.0, min(1.0, candidate.evidence_availability))
    prior = POPULARITY_PRIORS.get(_canonical_name(candidate.name), 0.0)
    return max(base, prior)


def _heuristic_score(spec: ScenarioSpec, candidate: CelebrityCandidate) -> tuple[float, float]:
    scenario_tokens = _tokenize(" ".join([spec.raw_user_query, *spec.domain_tags, *spec.task_types]))
    candidate_tokens = _tokenize(" ".join([candidate.name, candidate.description, *candidate.domains]))
    overlap = len(scenario_tokens & candidate_tokens)
    overlap_score = min(1.0, overlap / max(4, len(spec.domain_tags) + 2))
    domain_alignment, domain_mismatch_penalty = _domain_alignment_score(spec, candidate)

    anti_fit_penalty = 0.0
    lowered_name = candidate.name.lower()
    if any(token in lowered_name for token in ("list of", "culture of", "singer-songwriter", "record producer")):
        anti_fit_penalty += 0.25

    for domain in spec.domain_tags:
        forbidden = ANTI_FIT_HINTS.get(domain, set())
        if any(bad in candidate.description.lower() for bad in forbidden):
            anti_fit_penalty += 0.18

    anti_fit_penalty += domain_mismatch_penalty
    anti_fit_penalty = min(0.75, anti_fit_penalty)

    blended_base = (
        overlap_score * 0.30
        + domain_alignment * 0.25
        + candidate.distillability_score * 0.20
        + candidate.evidence_availability * 0.15
        + (1.0 - candidate.controversy_risk) * 0.05
        + min(1.0, len(candidate.domains) / 6.0) * 0.05
    )
    blended = blended_base - anti_fit_penalty

    return max(0.0, min(1.0, blended)), anti_fit_penalty


def _inject_user_includes(candidates: list[CelebrityCandidate], include_names: list[str]) -> list[CelebrityCandidate]:
    existing = {_canonical_name(candidate.name) for candidate in candidates}
    out = list(candidates)
    for raw_name in include_names:
        name = raw_name.strip()
        norm = _canonical_name(name)
        if not name or norm in existing:
            continue
        profile = NORMALIZED_USER_INCLUDE_PROFILES.get(norm)
        description = (
            profile[0] if profile else "User-specified candidate for scenario-specific cognitive coverage."
        )
        domains = profile[1] if profile else ["custom-include"]
        out.append(
            CelebrityCandidate(
                name=name,
                description=description,
                domains=domains,
                verified_human=True,
                era="modern",
                fit_reasons=["User-specified include candidate."],
                evidence_availability=0.40,
                distillability_score=0.48,
                controversy_risk=0.30,
            )
        )
        existing.add(norm)
    return out


def _filter_excludes(candidates: list[CelebrityCandidate], exclude_names: set[str]) -> list[CelebrityCandidate]:
    if not exclude_names:
        return candidates
    return [candidate for candidate in candidates if _canonical_name(candidate.name) not in exclude_names]


def _coverage_map(spec: ScenarioSpec, selected: list[CelebrityCandidate]) -> dict[str, list[str]]:
    selected_tags = {candidate.name: _candidate_cognitive_tags(candidate) for candidate in selected}
    coverage: dict[str, list[str]] = defaultdict(list)
    axes = spec.evaluation_axes or _scenario_axes(spec)
    for axis in axes:
        axis_token = axis.lower().replace("-", "_").replace(" ", "_")
        for candidate in selected:
            tags = selected_tags[candidate.name]
            if axis_token in tags:
                coverage[axis].append(candidate.name)
        if not coverage[axis]:
            coverage[axis] = [candidate.name for candidate in selected[:2]]
    return dict(coverage)


def _jaccard_distance(a: set[str], b: set[str]) -> float:
    union = a | b
    if not union:
        return 0.0
    return 1.0 - (len(a & b) / len(union))


def _greedy_cognitive_selection(
    spec: ScenarioSpec,
    pool: list[CelebrityCandidate],
    target_size: int,
    preferred_names: set[str],
) -> list[CelebrityCandidate]:
    selected: list[CelebrityCandidate] = []
    remaining = list(pool)
    tag_map = {id(candidate): _candidate_cognitive_tags(candidate) for candidate in remaining}

    scenario_axes = _scenario_axes(spec)
    covered_axes: set[str] = set()
    selected_tags: set[str] = set()

    while remaining and len(selected) < target_size:
        best_idx = 0
        best_value = -1.0

        for idx, candidate in enumerate(remaining):
            tags = tag_map[id(candidate)]
            popularity = _popularity_proxy(candidate)

            axis_gain = len((set(scenario_axes) & tags) - covered_axes) / max(1, len(scenario_axes))
            tag_gain = len(tags - selected_tags) / max(1, len(tags))

            if selected:
                conflict_gain = sum(_jaccard_distance(tags, tag_map[id(item)]) for item in selected) / len(selected)
            else:
                conflict_gain = 0.6

            anti_pop_bias = (1.0 - popularity) if candidate.fit_score >= 0.45 else 0.0
            prefer_bonus = 0.18 if _canonical_name(candidate.name) in preferred_names else 0.0

            value = (
                0.35 * candidate.final_score
                + 0.25 * axis_gain
                + 0.20 * tag_gain
                + 0.15 * conflict_gain
                + 0.05 * anti_pop_bias
                + prefer_bonus
            )

            if value > best_value:
                best_idx = idx
                best_value = value

        picked = remaining.pop(best_idx)
        selected.append(picked)
        tags = tag_map[id(picked)]
        covered_axes |= set(scenario_axes) & tags
        selected_tags |= tags

    return selected


def rank_and_select_candidates(
    spec: ScenarioSpec,
    candidates: list[CelebrityCandidate],
    llm: LLMClient | None,
    min_agents: int,
    max_agents: int,
    requested_team_size: int | None = None,
    include_celebrities: list[str] | None = None,
    exclude_celebrities: list[str] | None = None,
    selection_mode: Literal["auto", "prefer", "strict"] = "auto",
) -> SelectionResult:
    include_celebrities = include_celebrities or []
    exclude_set = {_canonical_name(name) for name in (exclude_celebrities or []) if name.strip()}
    preferred_set = {_canonical_name(name) for name in include_celebrities if name.strip()}
    llm_retrieval_rationale: list[str] = []

    if not candidates:
        candidates = []

    candidates = _inject_user_includes(candidates, include_celebrities)
    candidates = _filter_excludes(candidates, exclude_set)
    min_required_for_retrieval = max(
        min_agents,
        requested_team_size or 0,
        len(include_celebrities) if include_celebrities else 4,
    )
    candidates, llm_retrieval_rationale = _inject_llm_retrieved_candidates(
        spec=spec,
        candidates=candidates,
        llm=llm,
        include_celebrities=include_celebrities,
        min_required=min_required_for_retrieval,
        max_new=10 if selection_mode != "strict" else 0,
    )

    if not candidates:
        return SelectionResult(
            selected=[],
            rejected=[],
            selection_rationale=["No verified candidates were retrieved after include/exclude constraints."],
            coverage_map={},
            requested_team_size=requested_team_size,
            actual_team_size=0,
        )

    scored: list[CelebrityCandidate] = []
    for candidate in candidates:
        fit_score, penalty = _heuristic_score(spec, candidate)
        candidate.fit_score = fit_score
        candidate.anti_fit_penalty = penalty
        candidate.final_score = fit_score
        if not candidate.fit_reasons:
            candidate.fit_reasons = [
                "Semantic overlap with scenario tags.",
                "Has enough public footprint for distillation.",
            ]
        if penalty > 0.1 and not candidate.anti_fit_reasons:
            candidate.anti_fit_reasons = ["Domain mismatch risk is non-trivial for this scenario."]
        scored.append(candidate)

    llm_bonus, llm_aspect_hints, llm_rank_rationale = _llm_rank_guidance(spec, scored, llm)
    if llm_bonus:
        for candidate in scored:
            canonical = _canonical_name(candidate.name)
            bonus = llm_bonus.get(canonical, 0.0)
            if bonus > 0.0:
                candidate.final_score = max(0.0, min(1.0, candidate.final_score + bonus))
                candidate.fit_reasons.append("LLM API ranking marked this candidate as high relevance.")

    scored.sort(key=lambda x: x.final_score, reverse=True)

    preferred_size = requested_team_size if requested_team_size and requested_team_size > 0 else min(6, max_agents)
    preferred_size = max(min_agents, min(max_agents, preferred_size))
    if selection_mode != "strict" and not include_celebrities:
        preferred_size = max(preferred_size, min(max_agents, 4))

    if selection_mode == "strict":
        strict_selected: list[CelebrityCandidate] = []
        locked: set[str] = set()
        for raw_name in include_celebrities:
            norm = _canonical_name(raw_name)
            if not norm or norm in locked:
                continue
            for candidate in scored:
                if _canonical_name(candidate.name) == norm:
                    strict_selected.append(candidate)
                    locked.add(norm)
                    break
        # strict mode keeps user-defined identities only
        strict_selected = strict_selected[: preferred_size if preferred_size > 0 else len(strict_selected)]
        rejected = [candidate for candidate in scored if candidate not in strict_selected]
        return SelectionResult(
            selected=strict_selected,
            rejected=rejected[:20],
            selection_rationale=[
                "Strict mode: selection locked to user-specified celebrities.",
                "Ranking used only to order and trim inside the locked set.",
            ],
            coverage_map=_coverage_map(spec, strict_selected),
            requested_team_size=requested_team_size,
            actual_team_size=len(strict_selected),
        )

    rank_pool = scored
    if selection_mode != "strict":
        viable = [candidate for candidate in scored if candidate.final_score >= 0.20]
        viability_floor = min(preferred_size, 4 if not include_celebrities else preferred_size)
        if len(viable) >= viability_floor:
            rank_pool = viable

    selected = _greedy_cognitive_selection(
        spec=spec,
        pool=rank_pool,
        target_size=preferred_size,
        preferred_names=preferred_set if selection_mode == "prefer" else set(),
    )
    if selection_mode != "strict" and not include_celebrities:
        selected = _ensure_aspect_diversity(
            spec=spec,
            selected=selected,
            ranked_pool=scored,
            target_size=preferred_size,
            min_aspects=4,
            llm_aspect_hints=llm_aspect_hints,
        )

    rejected = [candidate for candidate in scored if candidate not in selected]
    for candidate in rejected[:20]:
        if not candidate.anti_fit_reasons:
            candidate.anti_fit_reasons = ["Lower cognitive coverage gain than selected members."]

    rationale = [
        "Selection optimized cognitive coverage + complementarity + conflict productivity.",
        "Anti-popularity bias applied when fit scores were already adequate.",
        "Thematic fit remained a hard prerequisite before diversity bonuses.",
    ]
    if llm_retrieval_rationale:
        rationale.extend(llm_retrieval_rationale)
    if llm_rank_rationale:
        rationale.append("LLM API ranking rationale: " + " | ".join(llm_rank_rationale[:3]))
    if selection_mode != "strict" and not include_celebrities:
        rationale.append("No explicit user include list: enforced minimum 4 members across at least 4 cognitive aspects when possible.")

    if selection_mode == "prefer" and include_celebrities:
        rationale.append("Prefer mode: user-specified celebrities received inclusion bonus without hard lock.")

    return SelectionResult(
        selected=selected,
        rejected=rejected[:20],
        selection_rationale=rationale,
        coverage_map=_coverage_map(spec, selected),
        requested_team_size=requested_team_size,
        actual_team_size=len(selected),
    )
