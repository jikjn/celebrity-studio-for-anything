from __future__ import annotations

from datetime import datetime, timezone

from .llm import LLMClient
from .models import CapabilityVector, ScenarioSpec


# Keep source ASCII-safe while still matching Chinese keywords via unicode escapes.
_DOMAIN_HINTS: dict[str, tuple[str, ...]] = {
    "education": (
        "\u5347\u5b66",
        "\u5fd7\u613f",
        "\u9ad8\u8003",
        "\u4e13\u4e1a",
        "\u6559\u80b2",
        "admission",
        "college",
        "school",
        "education",
    ),
    "career": ("\u804c\u4e1a", "\u5c31\u4e1a", "career", "job", "resume"),
    "product": ("\u4ea7\u54c1", "app", "saas", "\u7528\u6237", "product", "feature"),
    "branding": ("\u54c1\u724c", "\u5b9a\u4f4d", "\u4f20\u64ad", "marketing", "brand", "audience"),
    "business": ("\u5546\u4e1a", "\u76c8\u5229", "\u589e\u957f", "roi", "business", "strategy"),
    "film": ("\u77ed\u5267", "\u7535\u5f71", "\u5267\u672c", "worldbuilding", "story", "cinema"),
    "music": (
        "\u97f3\u4e50",
        "\u6b4c\u66f2",
        "\u4f5c\u66f2",
        "\u6b4c\u8bcd",
        "\u7ca4\u8bed\u6b4c",
        "cantopop",
        "song",
        "music",
    ),
    "culture_fusion": (
        "\u4e2d\u56fd\u98ce",
        "\u8d5b\u535a\u670b\u514b",
        "\u878d\u5408",
        "fusion",
        "cyberpunk",
        "oriental",
    ),
    "sports": ("\u8bad\u7ec3", "\u7ade\u6280", "\u6bd4\u8d5b", "performance", "sport"),
    "policy": ("\u653f\u7b56", "\u6cbb\u7406", "\u6cd5\u52a1", "compliance", "regulation"),
    "science": ("\u79d1\u7814", "\u8bba\u6587", "\u5b9e\u9a8c", "research", "scientific"),
}


def _now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _detect_language(raw_query: str, language_hint: str | None) -> str:
    if language_hint:
        return language_hint
    has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in raw_query)
    return "zh-CN" if has_cjk else "en-US"


def _infer_domains(raw_query: str) -> list[str]:
    lowered = raw_query.lower()
    tags: list[str] = []
    for tag, hints in _DOMAIN_HINTS.items():
        if any(hint.lower() in lowered for hint in hints):
            tags.append(tag)
    if not tags:
        tags = ["strategy", "general"]
    return tags


def _infer_task_types(raw_query: str) -> list[str]:
    lowered = raw_query.lower()
    task_types: list[str] = []

    if any(
        x in lowered
        for x in (
            "\u662f\u5426",
            "\u8981\u4e0d\u8981",
            "should",
            "whether",
            "\u51b3\u7b56",
            "decision",
        )
    ):
        task_types.append("decision")

    if any(x in lowered for x in ("\u89c4\u5212", "\u8def\u5f84", "plan", "roadmap")):
        task_types.append("planning")

    if any(x in lowered for x in ("\u5b9a\u4f4d", "strategy", "\u65b9\u6848", "approach")):
        task_types.append("strategy")

    if any(x in lowered for x in ("\u521b\u610f", "world", "\u5267", "creative", "design")):
        task_types.append("creativity")

    if not task_types:
        task_types = ["analysis"]
    return task_types


def _build_capability_vector(domain_tags: list[str]) -> CapabilityVector:
    base = CapabilityVector(
        strategy=0.55,
        creativity=0.40,
        pedagogy=0.35,
        operational_execution=0.45,
        realism=0.55,
        taste=0.35,
        persuasion=0.40,
        systems_thinking=0.45,
        ethics=0.30,
        mass_appeal=0.35,
        elite_competition=0.30,
        uncertainty_handling=0.45,
    )

    if "education" in domain_tags:
        base.pedagogy = 0.85
        base.realism = 0.80
        base.strategy = 0.70

    if "product" in domain_tags or "branding" in domain_tags:
        base.creativity = 0.80
        base.taste = 0.80
        base.mass_appeal = 0.75

    if "business" in domain_tags:
        base.operational_execution = 0.85
        base.strategy = 0.85

    if "music" in domain_tags:
        base.creativity = 0.88
        base.taste = 0.85
        base.mass_appeal = 0.80
        base.persuasion = 0.72

    if "culture_fusion" in domain_tags:
        base.creativity = max(base.creativity, 0.85)
        base.systems_thinking = max(base.systems_thinking, 0.70)
        base.uncertainty_handling = max(base.uncertainty_handling, 0.65)

    if "sports" in domain_tags:
        base.elite_competition = 0.85
        base.operational_execution = 0.75

    return base


def _heuristic_parse(raw_query: str, language: str) -> ScenarioSpec:
    domains = _infer_domains(raw_query)
    task_types = _infer_task_types(raw_query)
    return ScenarioSpec(
        scenario_id=f"scenario-{_now_id()}",
        raw_user_query=raw_query.strip(),
        language=language,
        domain_tags=domains,
        task_types=task_types,
        target_user_profile=[],
        desired_output=["consensus_map", "disagreement_map", "conditional_plan"],
        constraints=[],
        evaluation_axes=["thematic-fit", "execution", "risk", "long-term-value", "ethics"],
        capability_vector=_build_capability_vector(domains),
        reasoning_summary="Heuristic parser used as fallback.",
    )


def _llm_parse(raw_query: str, language: str, llm: LLMClient) -> ScenarioSpec:
    system_prompt = (
        "You are an intent parser for a celebrity multi-agent studio. "
        "Extract a normalized ScenarioSpec from user input. "
        "Return JSON only."
    )
    user_prompt = (
        "Parse this user query into JSON with keys: "
        "domain_tags, task_types, target_user_profile, desired_output, constraints, "
        "evaluation_axes, capability_vector, reasoning_summary.\n"
        f"language={language}\n"
        f"query={raw_query}"
    )
    parsed = llm.complete_json(system_prompt, user_prompt)
    return ScenarioSpec(
        scenario_id=f"scenario-{_now_id()}",
        raw_user_query=raw_query.strip(),
        language=language,
        domain_tags=parsed.get("domain_tags", []),
        task_types=parsed.get("task_types", []),
        target_user_profile=parsed.get("target_user_profile", []),
        desired_output=parsed.get("desired_output", []),
        constraints=parsed.get("constraints", []),
        evaluation_axes=parsed.get("evaluation_axes", []),
        capability_vector=CapabilityVector(**parsed.get("capability_vector", {})),
        reasoning_summary=parsed.get("reasoning_summary", ""),
    )


def parse_scenario(raw_query: str, llm: LLMClient | None, language_hint: str | None = None) -> ScenarioSpec:
    language = _detect_language(raw_query, language_hint)

    if llm is None:
        parsed = _heuristic_parse(raw_query, language)
    else:
        try:
            parsed = _llm_parse(raw_query, language, llm)
        except Exception:
            parsed = _heuristic_parse(raw_query, language)

    if not parsed.domain_tags:
        parsed.domain_tags = _infer_domains(raw_query)
    if not parsed.task_types:
        parsed.task_types = _infer_task_types(raw_query)
    if not parsed.evaluation_axes:
        parsed.evaluation_axes = ["thematic-fit", "execution", "risk", "long-term-value", "ethics"]

    return parsed
