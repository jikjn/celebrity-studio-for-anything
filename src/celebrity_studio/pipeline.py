from __future__ import annotations

from pathlib import Path
import re
from typing import Literal

from .celebrity_ranker import rank_and_select_candidates
from .celebrity_retriever import retrieve_candidates
from .config import Settings
from .debate_engine import run_debate
from .distillation_engine import distill_selected_candidates
from .models import CelebrityCandidate, PipelineRunResult, RuntimeConfig
from .providers import build_registry, registry_to_llm_adapter
from .result_formatter import render_markdown_report
from .scenario_parser import parse_scenario
from .studio_orchestrator import compose_studio
from .utils import ensure_dir, write_json, write_text


def _redacted_runtime(runtime: RuntimeConfig) -> RuntimeConfig:
    payload = runtime.model_dump()
    for provider in payload.get("providers", []):
        if provider.get("api_key"):
            provider["api_key"] = "[REDACTED]"
    return RuntimeConfig(**payload)


def _fallback_candidates_from_llm(
    scenario: object,
    llm: object | None,
    count: int,
    include_celebrities: list[str] | None = None,
) -> list[CelebrityCandidate]:
    if llm is None:
        return []
    include_celebrities = include_celebrities or []
    include_note = ", ".join(name for name in include_celebrities if name.strip()) or "(none)"
    raw_query = str(getattr(scenario, "raw_user_query", ""))
    domain_tags = list(getattr(scenario, "domain_tags", []))
    task_types = list(getattr(scenario, "task_types", []))
    language = str(getattr(scenario, "language", "zh-CN"))
    min_target = max(4, count)
    try:
        parsed = llm.complete_json(  # type: ignore[attr-defined]
            system_prompt=(
                "You are a public-figure retrieval engine for a multi-agent studio. "
                "Return only concrete people and keep thematic relevance high."
            ),
            user_prompt=(
                "Task: Please retrieve public figures relevant to the theme.\n"
                f"Theme: {raw_query}\n"
                f"Domain tags: {domain_tags}\n"
                f"Task types: {task_types}\n"
                f"Language: {language}\n"
                f"User required figures: {include_note}\n"
                f"Selection rule: diversify fields whenever possible. If user did not specify, return at least {min_target} people.\n"
                "Return JSON with key candidates: "
                "{\"candidates\":[{\"name\":\"\",\"description\":\"\",\"domains\":[],\"aspect\":\"\",\"reason\":\"\",\"field\":\"\"}]}"
            ),
        )
    except Exception:
        return []
    items = parsed.get("candidates", [])
    output: list[CelebrityCandidate] = []
    for item in items:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        output.append(
            CelebrityCandidate(
                name=name,
                description=str(item.get("description", "")),
                domains=[str(x) for x in item.get("domains", [])],
                verified_human=True,
                era="modern",
                fit_reasons=["LLM dynamic fallback candidate."],
                evidence_availability=0.35,
                distillability_score=0.40,
                controversy_risk=0.35,
            )
        )
    return output


def _fallback_candidates_heuristic(scenario: object, count: int) -> list[CelebrityCandidate]:
    domain_tags = [str(tag).lower() for tag in getattr(scenario, "domain_tags", [])]
    seeds: list[tuple[str, str, list[str]]] = [
        ("Charlie Munger", "Investor-thinker known for multidisciplinary decision models.", ["business", "decision making"]),
        ("Derek Sivers", "Builder and writer focused on practical execution and independent thinking.", ["product", "execution"]),
        ("Maria Montessori", "Educator focused on learner-centric pedagogy and structured autonomy.", ["education", "pedagogy"]),
        ("Donella Meadows", "Systems thinker on leverage points and policy dynamics.", ["systems", "policy"]),
        ("Brené Brown", "Researcher and communicator on leadership and human factors.", ["humanist", "communication"]),
    ]
    if "music" in domain_tags:
        seeds.extend(
            [
                ("Jay Chou", "Singer-songwriter and producer with strong East-West fusion capability.", ["music", "songwriting"]),
                ("Lin Xi", "Cantonese lyricist with symbolic compression and language precision.", ["lyrics", "cantopop"]),
                ("Yoko Kanno", "Composer known for cross-genre arrangement and narrative sound.", ["music", "composition"]),
            ]
        )
    if "culture_fusion" in domain_tags:
        seeds.extend(
            [
                ("Wong Kar-wai", "Film auteur with urban mood and cultural atmosphere design.", ["worldbuilding", "cinema"]),
                ("Mamoru Oshii", "Director/writer focused on cyberpunk ontology and identity conflict.", ["cyberpunk", "systems thinking"]),
            ]
        )
    if "science" in domain_tags:
        seeds.extend(
            [
                ("Richard Feynman", "Physicist known for first-principles and explanation clarity.", ["science", "first-principles"]),
                ("Jane Goodall", "Researcher known for longitudinal field evidence and observation discipline.", ["science", "research"]),
            ]
        )

    out: list[CelebrityCandidate] = []
    seen: set[str] = set()
    for name, description, domains in seeds:
        key = name.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(
            CelebrityCandidate(
                name=name,
                description=description,
                domains=domains,
                verified_human=True,
                era="modern",
                fit_reasons=["Heuristic fallback candidate when retrieval coverage is insufficient."],
                evidence_availability=0.34,
                distillability_score=0.40,
                controversy_risk=0.32,
            )
        )
        if len(out) >= count:
            break
    return out


def _deduplicate_candidates(candidates: list[CelebrityCandidate]) -> list[CelebrityCandidate]:
    dedup: dict[str, CelebrityCandidate] = {}
    for candidate in candidates:
        key = candidate.name.strip().lower()
        if key and key not in dedup:
            dedup[key] = candidate
    return list(dedup.values())


def _ensure_minimum_selection(
    selected: list[CelebrityCandidate],
    candidate_pool: list[CelebrityCandidate],
    min_agents: int,
) -> list[CelebrityCandidate]:
    result = list(selected)
    if len(result) >= min_agents:
        return result
    for candidate in candidate_pool:
        if candidate not in result:
            result.append(candidate)
        if len(result) >= min_agents:
            break
    return result


def _dedup_names(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        value = raw.strip()
        key = value.lower()
        if not value or key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _split_inline_name_list(text: str) -> list[str]:
    cleaned = text.strip().strip("[](){}")
    if not cleaned:
        return []
    parts = re.split(r"[,\uFF0C\u3001;/\uFF1B|]+|\s+and\s+|\s+AND\s+|\s+和\s+", cleaned)
    return [part.strip(" \t'\"`") for part in parts if part.strip(" \t'\"`")]


def _extract_inline_constraints(query: str) -> tuple[list[str], list[str]]:
    include: list[str] = []
    exclude: list[str] = []
    include_patterns = [
        r"(?:must\s+include|include(?:\s+celebrities)?|包含|必须包含|要求包含)\s*[:：]\s*([^\n。！？!?]+)",
    ]
    exclude_patterns = [
        r"(?:exclude|must\s+exclude|排除|不包含|不要)\s*[:：]\s*([^\n。！？!?]+)",
    ]
    for pattern in include_patterns:
        for match in re.finditer(pattern, query, flags=re.IGNORECASE):
            include.extend(_split_inline_name_list(match.group(1)))
    for pattern in exclude_patterns:
        for match in re.finditer(pattern, query, flags=re.IGNORECASE):
            exclude.extend(_split_inline_name_list(match.group(1)))
    return _dedup_names(include), _dedup_names(exclude)


def run_pipeline(
    query: str,
    requested_team_size: int | None = None,
    settings: Settings | None = None,
    output_root: Path | None = None,
    language_hint: str | None = None,
    runtime: RuntimeConfig | None = None,
    include_celebrities: list[str] | None = None,
    exclude_celebrities: list[str] | None = None,
    selection_mode: Literal["auto", "prefer", "strict"] = "auto",
) -> PipelineRunResult:
    settings = settings or Settings.from_env()
    runtime = runtime or RuntimeConfig()
    redacted_runtime = _redacted_runtime(runtime)
    output_root = output_root or settings.output_dir

    registry = build_registry(runtime=runtime, settings=settings)
    llm = registry_to_llm_adapter(registry)

    if runtime.strict_online and registry is None:
        raise RuntimeError("Strict online mode requires at least one configured provider.")

    inline_include, inline_exclude = _extract_inline_constraints(query)
    include_list = _dedup_names([*(include_celebrities or []), *inline_include])
    exclude_list = _dedup_names([*(exclude_celebrities or []), *inline_exclude])

    scenario = parse_scenario(query, llm, language_hint=language_hint)
    strict_locked = selection_mode == "strict" and bool(include_list)
    candidates: list[CelebrityCandidate] = []
    if not strict_locked:
        candidates = retrieve_candidates(scenario, llm)
        if len(candidates) < settings.min_agents:
            candidates.extend(
                _fallback_candidates_from_llm(
                    scenario,
                    llm,
                    count=max(settings.min_agents * 2, 8),
                    include_celebrities=include_list,
                )
            )
        if len(candidates) < settings.min_agents:
            candidates.extend(_fallback_candidates_heuristic(scenario, count=max(settings.min_agents * 2, 8)))
        candidates = _deduplicate_candidates(candidates)
    if len(candidates) < settings.min_agents and runtime.strict_online and not include_list:
        raise RuntimeError(
            "Insufficient candidates in strict_online mode. "
            "Please provide include_celebrities, improve provider quality, or disable strict_online."
        )
    if not candidates and not include_list:
        raise RuntimeError(
            "No candidates retrieved. Please provide explicit include_celebrities or configure a stronger online provider."
        )

    selection = rank_and_select_candidates(
        spec=scenario,
        candidates=candidates,
        llm=llm,
        min_agents=settings.min_agents,
        max_agents=settings.max_agents,
        requested_team_size=requested_team_size,
        include_celebrities=include_list,
        exclude_celebrities=exclude_list,
        selection_mode=selection_mode,
    )
    if selection_mode != "strict":
        selection.selected = _ensure_minimum_selection(selection.selected, candidates, settings.min_agents)
    selection.actual_team_size = len(selection.selected)

    skills = distill_selected_candidates(
        spec=scenario,
        selected=selection.selected,
        llm=llm,
        data_dir=settings.data_dir,
        realtime=runtime.realtime_distill,
        require_online=runtime.strict_online,
    )
    studio = compose_studio(scenario, selection, skills, llm)
    studio.max_rounds = max(2, runtime.discussion.min_turns_per_member + 1)
    style_hint = (runtime.discussion.interaction_style or "").strip()
    if style_hint:
        studio.discussion_protocol = f"Free-salon dynamic exchange. Style hint: {style_hint}"
    debate = run_debate(scenario, studio, skills, registry, discussion=runtime.discussion)
    report = render_markdown_report(scenario, selection, studio, debate, skills)

    run_dir = ensure_dir(output_root / scenario.scenario_id)
    write_json(run_dir / "scenario.json", scenario.model_dump())
    write_json(run_dir / "candidates.json", [item.model_dump() for item in candidates])
    write_json(run_dir / "selection.json", selection.model_dump())
    write_json(run_dir / "skills.json", [skill.model_dump() for skill in skills])
    write_json(run_dir / "studio.json", studio.model_dump())
    write_json(run_dir / "debate.json", debate.model_dump())
    write_json(run_dir / "runtime.json", redacted_runtime.model_dump())
    write_text(run_dir / "report.md", report)

    result = PipelineRunResult(
        scenario=scenario,
        selection=selection,
        skills=skills,
        studio=studio,
        debate=debate,
        runtime=redacted_runtime,
        report_markdown=report,
        run_dir=str(run_dir.resolve()),
    )
    write_json(run_dir / "result.json", result.model_dump())
    return result
