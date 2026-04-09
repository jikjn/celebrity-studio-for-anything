from __future__ import annotations

from collections import Counter

from celebrity_studio.celebrity_ranker import rank_and_select_candidates
from celebrity_studio.models import CapabilityVector, CelebrityCandidate, ScenarioSpec


def _spec(query: str = "I need a Cantonese cyberpunk song.") -> ScenarioSpec:
    return ScenarioSpec(
        scenario_id="test-selection",
        raw_user_query=query,
        language="zh-CN",
        domain_tags=["music", "culture_fusion"],
        task_types=["creation"],
        target_user_profile=[],
        desired_output=[],
        constraints=[],
        evaluation_axes=[],
        capability_vector=CapabilityVector(),
        reasoning_summary="",
    )


def test_strict_mode_built_in_profiles_for_chinese_names() -> None:
    include = [
        "\u5468\u6770\u4f26",  # Jay Chou
        "\u9ec4\u9711",  # James Wong
        "\u738b\u5bb6\u536b",  # Wong Kar-wai
        "\u6797\u5915",  # Lin Xi
        "\u62bc\u4e95\u5b88",  # Mamoru Oshii
    ]
    result = rank_and_select_candidates(
        spec=_spec(),
        candidates=[],
        llm=None,
        min_agents=1,
        max_agents=8,
        requested_team_size=5,
        include_celebrities=include,
        exclude_celebrities=[],
        selection_mode="strict",
    )

    assert [item.name for item in result.selected] == include
    for item in result.selected:
        assert item.description
        assert "User-specified candidate" not in item.description
        assert item.domains != ["custom-include"]


def test_include_alias_does_not_duplicate_existing_candidate() -> None:
    existing = CelebrityCandidate(
        name="\u5468\u6770\u502b",  # Jay Chou traditional
        description="Taiwanese singer-songwriter and producer.",
        domains=["music", "songwriting"],
        verified_human=True,
        era="modern",
        evidence_availability=0.5,
        distillability_score=0.5,
        controversy_risk=0.2,
    )
    result = rank_and_select_candidates(
        spec=_spec(),
        candidates=[existing],
        llm=None,
        min_agents=1,
        max_agents=6,
        requested_team_size=1,
        include_celebrities=["Jay Chou"],
        exclude_celebrities=[],
        selection_mode="strict",
    )

    names = [item.name for item in [*result.selected, *result.rejected]]
    assert names.count("\u5468\u6770\u502b") == 1
    assert len(result.selected) == 1


def test_exclude_alias_removes_candidate() -> None:
    candidate = CelebrityCandidate(
        name="\u738b\u5bb6\u536b",  # Wong Kar-wai
        description="Hong Kong film auteur.",
        domains=["cinema", "worldbuilding"],
        verified_human=True,
        era="modern",
        evidence_availability=0.5,
        distillability_score=0.5,
        controversy_risk=0.2,
    )
    result = rank_and_select_candidates(
        spec=_spec(),
        candidates=[candidate],
        llm=None,
        min_agents=1,
        max_agents=6,
        requested_team_size=1,
        include_celebrities=[],
        exclude_celebrities=["Wong Kar Wai"],
        selection_mode="auto",
    )

    assert result.selected == []
    assert result.actual_team_size == 0


def test_strict_mode_deduplicates_aliases_for_same_person() -> None:
    result = rank_and_select_candidates(
        spec=_spec(),
        candidates=[],
        llm=None,
        min_agents=1,
        max_agents=8,
        requested_team_size=4,
        include_celebrities=["Jay Chou", "\u5468\u6770\u4f26", "Zhou Jielun"],
        exclude_celebrities=[],
        selection_mode="strict",
    )

    assert len(result.selected) == 1


def test_generic_domain_strategy_demotes_cross_domain_noise() -> None:
    aligned = CelebrityCandidate(
        name="Jay Chou",
        description="Taiwanese singer-songwriter and producer.",
        domains=["music", "songwriting", "producer"],
        verified_human=True,
        era="modern",
        evidence_availability=0.5,
        distillability_score=0.5,
        controversy_risk=0.2,
    )
    mismatch = CelebrityCandidate(
        name="James Wong",
        description="Hong Kong photographer focused on street portraits.",
        domains=["photography", "visual art"],
        verified_human=True,
        era="modern",
        evidence_availability=0.5,
        distillability_score=0.5,
        controversy_risk=0.2,
    )

    result = rank_and_select_candidates(
        spec=_spec(),
        candidates=[mismatch, aligned],
        llm=None,
        min_agents=1,
        max_agents=6,
        requested_team_size=1,
        include_celebrities=[],
        exclude_celebrities=[],
        selection_mode="auto",
    )

    assert result.selected[0].name == "Jay Chou"
    scored = {item.name: item for item in [*result.selected, *result.rejected]}
    assert scored["Jay Chou"].final_score > scored["James Wong"].final_score


def test_no_include_defaults_to_four_members_and_four_aspects_when_possible() -> None:
    candidates = [
        CelebrityCandidate(
            name="A Composer",
            description="Composer and musician.",
            domains=["music", "composition"],
            verified_human=True,
            era="modern",
            evidence_availability=0.5,
            distillability_score=0.5,
            controversy_risk=0.2,
        ),
        CelebrityCandidate(
            name="A Film Auteur",
            description="Director known for cinematic worldbuilding.",
            domains=["film", "worldbuilding"],
            verified_human=True,
            era="modern",
            evidence_availability=0.5,
            distillability_score=0.5,
            controversy_risk=0.2,
        ),
        CelebrityCandidate(
            name="A Strategist",
            description="Business strategist and systems thinker.",
            domains=["business", "strategy"],
            verified_human=True,
            era="modern",
            evidence_availability=0.5,
            distillability_score=0.5,
            controversy_risk=0.2,
        ),
        CelebrityCandidate(
            name="A Humanist",
            description="Poet and cultural critic with language focus.",
            domains=["culture", "language", "lyrics"],
            verified_human=True,
            era="modern",
            evidence_availability=0.5,
            distillability_score=0.5,
            controversy_risk=0.2,
        ),
        CelebrityCandidate(
            name="A Producer",
            description="Operator and producer focused on execution.",
            domains=["operator", "production"],
            verified_human=True,
            era="modern",
            evidence_availability=0.5,
            distillability_score=0.5,
            controversy_risk=0.2,
        ),
    ]

    result = rank_and_select_candidates(
        spec=_spec(),
        candidates=candidates,
        llm=None,
        min_agents=1,
        max_agents=6,
        requested_team_size=2,
        include_celebrities=[],
        exclude_celebrities=[],
        selection_mode="auto",
    )

    assert len(result.selected) >= 4
    role_aspects = Counter()
    for item in result.selected:
        text = " ".join([item.description, *item.domains]).lower()
        if "music" in text or "composer" in text:
            role_aspects["music"] += 1
        elif "world" in text or "film" in text:
            role_aspects["world"] += 1
        elif "strategy" in text or "systems" in text:
            role_aspects["strategy"] += 1
        elif "language" in text or "culture" in text or "lyric" in text:
            role_aspects["humanist"] += 1
        elif "operator" in text or "production" in text:
            role_aspects["operator"] += 1
    assert len(role_aspects) >= 4


def test_llm_retrieval_prompt_includes_user_requirements_and_minimum_count() -> None:
    class _FakeLLM:
        def __init__(self) -> None:
            self.prompts: list[str] = []

        def complete_json(self, system_prompt: str, user_prompt: str) -> dict:  # type: ignore[override]
            self.prompts.append(user_prompt)
            if "key candidates" in user_prompt:
                return {
                    "candidates": [
                        {"name": "Lin Xi", "description": "Cantonese lyricist", "domains": ["lyrics", "cantopop"]},
                        {"name": "Jay Chou", "description": "Singer-songwriter", "domains": ["music", "songwriting"]},
                    ]
                }
            return {"picks": []}

    llm = _FakeLLM()
    result = rank_and_select_candidates(
        spec=_spec(),
        candidates=[],
        llm=llm,  # type: ignore[arg-type]
        min_agents=1,
        max_agents=8,
        requested_team_size=2,
        include_celebrities=["Jay Chou", "Lin Xi"],
        exclude_celebrities=[],
        selection_mode="prefer",
    )

    retrieval_prompt = next(prompt for prompt in llm.prompts if "key candidates" in prompt)
    assert "User required figures: Jay Chou, Lin Xi" in retrieval_prompt
    assert "diversify fields whenever possible" in retrieval_prompt
    assert "at least 4 people" in retrieval_prompt
    assert result.actual_team_size >= 2
