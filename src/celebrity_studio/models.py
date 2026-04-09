from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .utils import utc_now_iso


class CapabilityVector(BaseModel):
    strategy: float = 0.0
    creativity: float = 0.0
    pedagogy: float = 0.0
    operational_execution: float = 0.0
    realism: float = 0.0
    taste: float = 0.0
    persuasion: float = 0.0
    systems_thinking: float = 0.0
    ethics: float = 0.0
    mass_appeal: float = 0.0
    elite_competition: float = 0.0
    uncertainty_handling: float = 0.0

    @field_validator("*")
    @classmethod
    def _clamp(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))


class ScenarioSpec(BaseModel):
    scenario_id: str
    raw_user_query: str
    language: str = "zh-CN"
    domain_tags: list[str] = Field(default_factory=list)
    task_types: list[str] = Field(default_factory=list)
    target_user_profile: list[str] = Field(default_factory=list)
    desired_output: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    evaluation_axes: list[str] = Field(default_factory=list)
    capability_vector: CapabilityVector = Field(default_factory=CapabilityVector)
    reasoning_summary: str = ""
    created_at: str = Field(default_factory=utc_now_iso)


class CelebrityCandidate(BaseModel):
    name: str
    name_native: str | None = None
    wikidata_id: str | None = None
    wikipedia_url: str | None = None
    description: str = ""
    era: Literal["ancient", "modern", "contemporary"] = "modern"
    region: str = "global"
    domains: list[str] = Field(default_factory=list)
    verified_human: bool = False
    fit_score: float = 0.0
    anti_fit_penalty: float = 0.0
    final_score: float = 0.0
    fit_reasons: list[str] = Field(default_factory=list)
    anti_fit_reasons: list[str] = Field(default_factory=list)
    controversy_risk: float = 0.0
    distillability_score: float = 0.0
    evidence_availability: float = 0.0
    complementarity_tags: list[str] = Field(default_factory=list)

    @field_validator("fit_score", "anti_fit_penalty", "final_score", "controversy_risk", "distillability_score", "evidence_availability")
    @classmethod
    def _bound_scores(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))


class SelectionResult(BaseModel):
    selected: list[CelebrityCandidate]
    rejected: list[CelebrityCandidate]
    selection_rationale: list[str] = Field(default_factory=list)
    coverage_map: dict[str, list[str]] = Field(default_factory=dict)
    requested_team_size: int | None = None
    actual_team_size: int = 0


class SourceAnchor(BaseModel):
    title: str
    url: str
    source_type: Literal["book", "interview", "speech", "social", "biography", "wiki", "other"] = "other"
    note: str = ""


class MentalModel(BaseModel):
    name: str
    one_liner: str
    evidence: list[str] = Field(default_factory=list)
    application: str
    limitation: str


class DecisionHeuristic(BaseModel):
    name: str
    rule: str
    when_to_use: str
    counter_signal: str


class ExpressionDNA(BaseModel):
    tone: str
    rhythm: str
    lexical_markers: list[str] = Field(default_factory=list)
    taboo_phrasing: list[str] = Field(default_factory=list)
    challenge_style: str


class SkillIdentity(BaseModel):
    name: str
    era: str
    domains: list[str] = Field(default_factory=list)
    confidence: float = 0.0

    @field_validator("confidence")
    @classmethod
    def _bound_confidence(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))


class DistilledSkill(BaseModel):
    slug: str
    identity: SkillIdentity
    mental_models: list[MentalModel] = Field(default_factory=list)
    decision_heuristics: list[DecisionHeuristic] = Field(default_factory=list)
    expression_dna: ExpressionDNA
    values_and_taboo: list[str] = Field(default_factory=list)
    blindspots: list[str] = Field(default_factory=list)
    uncertainty_policy: str
    honest_boundaries: list[str] = Field(default_factory=list)
    best_fit_scenarios: list[str] = Field(default_factory=list)
    worst_fit_scenarios: list[str] = Field(default_factory=list)
    collaboration_role: str
    source_anchors: list[SourceAnchor] = Field(default_factory=list)
    generated_at: str = Field(default_factory=utc_now_iso)
    version: str = "0.1.0"


class StudioMember(BaseModel):
    agent_id: str
    celebrity_name: str
    skill_slug: str
    role_in_studio: str
    speaking_style: str
    challenge_style: str
    provider_id: str = "default"
    session_id: str = ""


class StudioConfig(BaseModel):
    scenario_id: str
    leader: str = "studio-leader"
    members: list[StudioMember] = Field(default_factory=list)
    reserve_members: list[StudioMember] = Field(default_factory=list)
    discussion_protocol: str = ""
    max_rounds: int = 6
    stop_conditions: list[str] = Field(default_factory=list)


class Task(BaseModel):
    id: str
    owner: str
    description: str
    dependencies: list[str] = Field(default_factory=list)
    status: Literal["todo", "doing", "done"] = "todo"


class Message(BaseModel):
    id: str
    phase: str
    round_no: int
    from_agent: str
    to_agent: str = "all"
    type: Literal["claim", "challenge", "defense", "revision", "synthesis", "note"] = "note"
    content: str
    refs: list[str] = Field(default_factory=list)
    provider_id: str = ""
    target_message_id: str | None = None
    objection_type: Literal["evidence", "feasibility", "ethics", "timescale", "user-fit", "scope", "other"] | None = None
    severity: Literal[1, 2, 3] | None = None
    created_at: str = Field(default_factory=utc_now_iso)


class RouteRecommendation(BaseModel):
    route_name: str
    description: str
    supporters: list[str] = Field(default_factory=list)
    opponents: list[str] = Field(default_factory=list)
    suitable_when: list[str] = Field(default_factory=list)
    avoid_when: list[str] = Field(default_factory=list)
    first_actions: list[str] = Field(default_factory=list)


class SynthesisResult(BaseModel):
    consensus_points: list[str] = Field(default_factory=list)
    disagreement_points: list[str] = Field(default_factory=list)
    reservation_points: list[str] = Field(default_factory=list)
    conditional_recommendations: list[RouteRecommendation] = Field(default_factory=list)
    final_synthesis: str = ""


class ChallengeEdge(BaseModel):
    source: str
    target: str
    count: int = 1
    latest_message_id: str = ""


class DebateSession(BaseModel):
    studio_id: str
    tasks: list[Task] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    rounds_completed: int = 0
    synthesis: SynthesisResult = Field(default_factory=SynthesisResult)
    missing_viewpoints: list[str] = Field(default_factory=list)
    dynamic_added_members: list[str] = Field(default_factory=list)
    challenge_edges: list[ChallengeEdge] = Field(default_factory=list)


class ProviderConfig(BaseModel):
    provider_id: str = "default"
    provider_type: Literal["openai_compatible", "codex_cli"] = "openai_compatible"
    model: str = "gpt-4.1"
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.3
    timeout_s: int = 300
    extra_headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("temperature")
    @classmethod
    def _temperature_range(cls, value: float) -> float:
        return max(0.0, min(2.0, float(value)))


class DiscussionConfig(BaseModel):
    mode: Literal["free_salon"] = "free_salon"
    min_turns_per_member: int = 5
    turn_length: Literal["brief", "standard", "long", "extended"] = "long"
    interaction_style: str = (
        "像同桌沙龙一样自由交流，允许质疑、支持、反驳、补充，不走模板话术，优先真实观点碰撞。"
    )

    @field_validator("min_turns_per_member")
    @classmethod
    def _turns_range(cls, value: int) -> int:
        return max(1, min(12, int(value)))

    @field_validator("interaction_style")
    @classmethod
    def _style_non_empty(cls, value: str) -> str:
        text = (value or "").strip()
        if text:
            return text
        return "像同桌沙龙一样自由交流，允许质疑、支持、反驳、补充，不走模板话术，优先真实观点碰撞。"


class RuntimeConfig(BaseModel):
    providers: list[ProviderConfig] = Field(default_factory=list)
    default_provider_id: str = "default"
    leader_provider_id: str | None = None
    assignment_strategy: Literal["round_robin", "default_only"] = "round_robin"
    realtime_distill: bool = True
    strict_online: bool = True
    discussion: DiscussionConfig = Field(default_factory=DiscussionConfig)


class PipelineRunResult(BaseModel):
    scenario: ScenarioSpec
    selection: SelectionResult
    skills: list[DistilledSkill]
    studio: StudioConfig
    debate: DebateSession
    runtime: RuntimeConfig | None = None
    report_markdown: str
    run_dir: str
    created_at: str = Field(default_factory=utc_now_iso)
