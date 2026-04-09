from __future__ import annotations

import tempfile
from pathlib import Path

import celebrity_studio.pipeline as pipeline_module
from celebrity_studio.config import Settings
from celebrity_studio.agent_runtime import build_leader_system_prompt, build_member_system_prompt
from celebrity_studio.debate_engine import _augment_with_agent_details, _ensure_task_answer
from celebrity_studio.models import CapabilityVector, Message, RouteRecommendation, RuntimeConfig, ScenarioSpec
from celebrity_studio.pipeline import _extract_inline_constraints
from celebrity_studio.models import DistilledSkill, ExpressionDNA, SkillIdentity, StudioMember


def _spec() -> ScenarioSpec:
    return ScenarioSpec(
        scenario_id="test-guardrails",
        raw_user_query="I want a Cantonese cyberpunk song with Chinese aesthetics.",
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


def test_inline_constraint_extraction_from_query() -> None:
    include, exclude = _extract_inline_constraints(
        "\u6211\u60f3\u505a\u4e00\u9996\u6b4c\u3002\u5305\u542b: "
        "\u5468\u6770\u4f26\u3001\u9ec4\u9711, \u738b\u5bb6\u536b\u3002"
        "\u6392\u9664: \u66f9\u64cd, Donald Trump"
    )
    assert include == ["\u5468\u6770\u4f26", "\u9ec4\u9711", "\u738b\u5bb6\u536b"]
    assert exclude == ["\u66f9\u64cd", "Donald Trump"]


def test_ensure_task_answer_rewrites_process_only_text() -> None:
    route = RouteRecommendation(
        route_name="Signal-first Route",
        description="Ship a minimal draft and iterate from real listener signal.",
        supporters=["Jay Chou"],
        opponents=[],
        suitable_when=["feedback loop is available"],
        avoid_when=["no iteration window exists"],
        first_actions=["Write hook + chorus draft", "Produce 30-second demo"],
    )
    out = _ensure_task_answer(
        spec=_spec(),
        answer="Use a six-phase workflow with agent orchestration and gate checks.",
        routes=[route],
    )
    assert "歌名方向" in out
    assert "意象池" in out
    assert "I want a Cantonese cyberpunk song with Chinese aesthetics." in out


def test_ensure_task_answer_keeps_existing_detail_for_song_case() -> None:
    route = RouteRecommendation(
        route_name="Signal-first Route",
        description="Ship a minimal draft and iterate from real listener signal.",
        supporters=["Jay Chou"],
        opponents=[],
        suitable_when=["feedback loop is available"],
        avoid_when=["no iteration window exists"],
        first_actions=["Write hook + chorus draft", "Produce 30-second demo"],
    )
    detailed = "陈奕迅建议副歌每句控制在8到10字并优先保证两遍可跟唱。"
    out = _ensure_task_answer(spec=_spec(), answer=detailed, routes=[route])
    assert detailed in out
    assert "歌名方向" in out


def test_augment_with_agent_details_includes_member_specific_points() -> None:
    messages = [
        Message(
            id="msg-0001",
            phase="salon-flow-r02",
            round_no=2,
            from_agent="陈奕迅",
            to_agent="all",
            type="note",
            content="我的建议是副歌每句8到10字，前45秒必须出现可复唱的主钩。",
        ),
        Message(
            id="msg-0002",
            phase="salon-flow-r02",
            round_no=2,
            from_agent="林夕",
            to_agent="all",
            type="challenge",
            content="我不同意只追求顺口，必须保留一句有刺点的语义冲突，不然听感会太平。",
        ),
    ]
    base = "最终建议：先做一版可执行草案并进行小范围试听。"
    out = _augment_with_agent_details(base, messages, ["陈奕迅", "林夕"])
    assert "各 Agent 关键观点汇总" in out
    assert "- 陈奕迅:" in out
    assert "- 林夕:" in out


def test_augment_with_agent_details_prefers_substantive_clauses_over_turn_taking_boilerplate() -> None:
    messages = [
        Message(
            id="msg-0101",
            phase="salon-flow-r04",
            round_no=4,
            from_agent="巴菲特",
            to_agent="all",
            type="revision",
            content=(
                "我先接主持人的问题，也回应爱玲和村上；"
                "我建议把婚恋稳定性拆成三项：责任兑现、冲突修复、财务边界，"
                "每项10分，低于7分不加码承诺。"
            ),
        ),
    ]
    base = "最终建议：先形成可执行框架。"
    out = _augment_with_agent_details(base, messages, ["巴菲特"])
    assert "- 巴菲特:" in out
    assert "责任兑现" in out
    assert "低于7分不加码承诺" in out
    assert "我先接主持人的问题" not in out


def test_strict_with_include_skips_retrieval() -> None:
    workspace = Path(__file__).resolve().parents[1]
    settings = Settings.from_env(workspace_root=workspace)
    settings.offline = True
    settings.min_agents = 1
    settings.max_agents = 4

    original_retrieve = pipeline_module.retrieve_candidates

    def _should_not_call(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("retrieve_candidates should be skipped in strict mode with include list.")

    try:
        pipeline_module.retrieve_candidates = _should_not_call  # type: ignore[assignment]
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = pipeline_module.run_pipeline(
                query="Compose a song. include: Jay Chou",
                settings=settings,
                output_root=Path(tmp_dir),
                language_hint="en-US",
                runtime=RuntimeConfig(strict_online=False, realtime_distill=False),
                include_celebrities=["Jay Chou"],
                selection_mode="strict",
                requested_team_size=1,
            )
        assert result.selection.actual_team_size >= 1
    finally:
        pipeline_module.retrieve_candidates = original_retrieve  # type: ignore[assignment]


def test_language_hint_is_embedded_in_system_prompts() -> None:
    spec = _spec().model_copy(update={"language": "zh-CN"})
    skill = DistilledSkill(
        slug="jay-chou",
        identity=SkillIdentity(name="Jay Chou", era="modern", domains=["music"], confidence=0.9),
        mental_models=[],
        decision_heuristics=[],
        expression_dna=ExpressionDNA(
            tone="Hook-forward",
            rhythm="Short memorable clauses -> image punchline -> melodic landing",
            lexical_markers=["hook"],
            taboo_phrasing=["flat chorus"],
            challenge_style="Challenge hook quality.",
        ),
        values_and_taboo=[],
        blindspots=[],
        uncertainty_policy="Bounded uncertainty.",
        honest_boundaries=[],
        best_fit_scenarios=[],
        worst_fit_scenarios=[],
        collaboration_role="Hook Architect",
    )
    member = StudioMember(
        agent_id="agent-01",
        celebrity_name="Jay Chou",
        skill_slug="jay-chou",
        role_in_studio="Hook Architect",
        speaking_style="Hook-forward",
        challenge_style="Challenge hook quality.",
    )
    member_prompt = build_member_system_prompt(member, skill, spec)
    leader_prompt = build_leader_system_prompt(spec)
    assert "Scenario language: zh-CN" in member_prompt
    assert "Scenario language: zh-CN" in leader_prompt
    assert "Use Chinese for all responses" in member_prompt
