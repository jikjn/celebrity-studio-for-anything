from __future__ import annotations

from itertools import cycle

from .llm import LLMClient
from .models import DistilledSkill, ScenarioSpec, SelectionResult, StudioConfig, StudioMember
from .utils import slugify_name


ROLE_FALLBACKS = [
    "Visionary",
    "Critic",
    "Operator",
    "Realist",
    "Humanist",
    "Synthesizer",
    "Contrarian",
    "Systems Thinker",
]

ROLE_GUARDRAIL_WORDS = {"lead", "manager", "coordinator", "owner", "executor", "director of"}


def _normalize_role(role: str, fallback: str) -> str:
    cleaned = role.strip()
    if not cleaned:
        return fallback
    lower = cleaned.lower()
    if any(token in lower for token in ROLE_GUARDRAIL_WORDS):
        return fallback
    return cleaned


def _default_discussion_protocol() -> str:
    return (
        "Open salon kickoff -> dynamic free-salon dialogue with natural challenge/support "
        "-> host-led synthesis into executable recommendations"
    )


def _skills_to_members(skills: list[DistilledSkill]) -> list[StudioMember]:
    members: list[StudioMember] = []
    fallback_roles = cycle(ROLE_FALLBACKS)
    for idx, skill in enumerate(skills, start=1):
        fallback = next(fallback_roles)
        role = _normalize_role(skill.collaboration_role or fallback, fallback)
        members.append(
            StudioMember(
                agent_id=f"agent-{idx:02d}-{slugify_name(skill.identity.name)}",
                celebrity_name=skill.identity.name,
                skill_slug=skill.slug,
                role_in_studio=role,
                speaking_style=skill.expression_dna.tone,
                challenge_style=skill.expression_dna.challenge_style,
            )
        )
    return members


def _reserve_members(selection: SelectionResult, existing_names: set[str]) -> list[StudioMember]:
    reserve: list[StudioMember] = []
    for idx, candidate in enumerate(selection.rejected[:3], start=1):
        if candidate.name in existing_names:
            continue
        reserve.append(
            StudioMember(
                agent_id=f"reserve-{idx:02d}-{slugify_name(candidate.name)}",
                celebrity_name=candidate.name,
                skill_slug=slugify_name(candidate.name),
                role_in_studio="Reserve Perspective",
                speaking_style="Concise analytical",
                challenge_style="Focus on anti-fit and edge cases",
            )
        )
    return reserve


def compose_studio(
    spec: ScenarioSpec,
    selection: SelectionResult,
    skills: list[DistilledSkill],
    llm: LLMClient | None,
) -> StudioConfig:
    members = _skills_to_members(skills)
    if llm is not None and members:
        try:
            payload = llm.complete_json(
                system_prompt="Assign cognitive functions for an Open Studio Field collaboration.",
                user_prompt=(
                    "Return JSON with key role_map where key is celebrity name and value is cognitive-function string.\n"
                    "Use cognitive function labels, not job titles.\n"
                    "Allowed core functions include: Visionary, Realist, Humanist, Operator, Critic, "
                    "Synthesizer, Worldbuilder, Taste Curator, Systems Thinker, Hook Architect, Cultural Spine.\n"
                    "Domain lens suffix is allowed (example: 'Hook Architect: Cantonese Prosody').\n"
                    f"scenario={spec.model_dump()}\n"
                    f"members={[m.model_dump() for m in members]}"
                ),
            )
            role_map = payload.get("role_map", {})
            for member in members:
                new_role = role_map.get(member.celebrity_name)
                if isinstance(new_role, str) and new_role.strip():
                    member.role_in_studio = _normalize_role(new_role, member.role_in_studio)
        except Exception:
            pass
    reserve = _reserve_members(selection, existing_names={m.celebrity_name for m in members})
    return StudioConfig(
        scenario_id=spec.scenario_id,
        leader="studio-leader",
        members=members,
        reserve_members=reserve,
        discussion_protocol=_default_discussion_protocol(),
        max_rounds=6,
        stop_conditions=[
            "Open Studio Field stages completed with at least one free-salon round.",
            "Emerging centers were surfaced before convergence.",
            "At least one conditional recommendation route is generated.",
        ],
    )
