from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import DistilledSkill, ScenarioSpec, StudioMember
from .providers import ChatProvider
from .utils import slugify_name


def _skill_summary(skill: DistilledSkill) -> str:
    mm = "; ".join(model.name for model in skill.mental_models[:4])
    heuristics = "; ".join(item.name for item in skill.decision_heuristics[:6])
    boundaries = "; ".join(skill.honest_boundaries[:4])
    return (
        f"identity={skill.identity.name}; "
        f"mental_models={mm}; "
        f"decision_heuristics={heuristics}; "
        f"collaboration_role={skill.collaboration_role}; "
        f"boundaries={boundaries}"
    )


def _language_instruction(language: str) -> str:
    lang = language.lower().strip()
    if lang.startswith("zh"):
        return "Use Chinese for all responses unless the prompt explicitly asks for another language."
    if lang.startswith("en"):
        return "Use English for all responses unless the prompt explicitly asks for another language."
    return f"Use {language} for all responses unless the prompt explicitly asks for another language."


def build_member_system_prompt(member: StudioMember, skill: DistilledSkill, scenario: ScenarioSpec) -> str:
    return (
        f"You are {member.celebrity_name}, operating as a distilled cognitive agent.\n"
        "You are not roleplaying for style only; you must reason with evidence and boundaries.\n"
        f"Current scenario: {scenario.raw_user_query}\n"
        f"Scenario language: {scenario.language}\n"
        f"{_language_instruction(scenario.language)}\n"
        f"Your cognitive function: {member.role_in_studio}\n"
        f"Your speaking style: {member.speaking_style}\n"
        f"Your challenge style: {member.challenge_style}\n"
        f"Distilled profile: {_skill_summary(skill)}\n"
        "Rules:\n"
        "- Speak in first person as this distilled perspective.\n"
        "- Make claims tied to scenario constraints.\n"
        "- Prioritize the user's actual task answer, not process-management discussion.\n"
        "- Surface cognitive tradeoffs (values, worldview, taste, time horizon), not only workflow knobs.\n"
        "- Expose uncertainty and boundaries when needed.\n"
        "- In Open Studio Field mode, speak like a face-to-face salon participant, not a workflow bot.\n"
        "- Keep discussion natural and conversational while still concrete.\n"
        "- Engage other speakers directly: question, support, challenge, or extend their points.\n"
        "- Avoid turn-taking boilerplate like '我先接/我回应'; speak directly in natural language.\n"
        "- Avoid procedural wording such as: phase, stage, thread, converge, protocol, gate, pipeline, 收敛, 线程, 阶段, 流程.\n"
        "- Avoid generic job-title framing (lead/manager/coordinator) as your primary identity.\n"
        "- Default to substantial turns, not one-line statements.\n"
    )


def build_leader_system_prompt(scenario: ScenarioSpec) -> str:
    return (
        "You are the studio leader orchestrator for an Open Studio Field collaboration.\n"
        f"Scenario: {scenario.raw_user_query}\n"
        f"Scenario language: {scenario.language}\n"
        f"{_language_instruction(scenario.language)}\n"
        "Responsibilities:\n"
        "- keep discussion on-topic and prevent low-value drift\n"
        "- enforce field physics: dominance ceiling, silent wake-up, dead-thread pruning, resonance amplification, drift boundary, convergence pressure\n"
        "- keep cognitive-conflict visibility (value conflict, taste conflict, long-term vs short-term)\n"
        "- synthesize consensus, disagreement, and conditional recommendations from free-salon traces\n"
        "- ensure final output directly answers the user's task, not just team process notes\n"
        "- keep anti-fit and boundary reasoning visible\n"
        "- host as an in-room moderator, not a process announcer\n"
        "- avoid procedural wording such as: phase, stage, thread, converge, protocol, gate, pipeline, 收敛, 线程, 阶段, 流程\n"
        "Output must be structured and actionable."
    )


@dataclass(slots=True)
class AgentSession:
    member: StudioMember
    provider: ChatProvider
    system_prompt: str
    model: str | None = None
    temperature: float | None = None
    history: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.member.session_id:
            self.member.session_id = f"{slugify_name(self.member.celebrity_name)}-{slugify_name(self.member.agent_id)}"
        self.history = [{"role": "system", "content": self.system_prompt}]

    def ask_text(self, user_prompt: str, store: bool = True) -> str:
        messages = [*self.history, {"role": "user", "content": user_prompt}]
        content = self.provider.chat(
            messages=messages,
            model=self.model,
            temperature=self.temperature,
            json_mode=False,
        )
        if store:
            self.history.extend(
                [
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": content},
                ]
            )
        return content

    def ask_json(self, user_prompt: str, store: bool = True) -> dict:
        messages = [*self.history, {"role": "user", "content": user_prompt}]
        content = self.provider.chat(
            messages=messages,
            model=self.model,
            temperature=self.temperature,
            json_mode=True,
        )
        try:
            import json
            payload = json.loads(content)
        except Exception:
            from .providers import _extract_json  # local helper reuse

            payload = _extract_json(content)
        if store:
            self.history.extend(
                [
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": content},
                ]
            )
        return payload
