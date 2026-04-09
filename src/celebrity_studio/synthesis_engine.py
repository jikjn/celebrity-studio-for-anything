from __future__ import annotations

from collections import Counter

from .llm import LLMClient
from .models import Message, RouteRecommendation, ScenarioSpec, StudioConfig, SynthesisResult


def _message_digest(messages: list[Message], limit: int = 40) -> list[dict]:
    return [
        {
            "phase": msg.phase,
            "from": msg.from_agent,
            "to": msg.to_agent,
            "type": msg.type,
            "content": msg.content,
        }
        for msg in messages[-limit:]
    ]


def _heuristic_synthesis(spec: ScenarioSpec, studio: StudioConfig, messages: list[Message]) -> SynthesisResult:
    interaction_msgs = [msg for msg in messages if msg.to_agent != "all"]
    convergence_msgs = [msg for msg in messages if msg.phase == "stage-d-natural-convergence"]
    term_counter = Counter()
    for msg in messages:
        for token in msg.content.lower().split():
            if len(token) >= 6 and token.isalpha():
                term_counter[token] += 1
    high_terms = [term for term, _ in term_counter.most_common(5)]
    consensus = [
        "Team agreed that thematic fit should dominate fame in agent selection.",
        "Team agreed to convert advice into conditional recommendations with explicit assumptions.",
    ]
    if high_terms:
        consensus.append(f"Frequent cross-agent themes: {', '.join(high_terms)}.")
    disagreements = [
        "Debate surfaced tradeoff between short-term feasibility and long-term positioning.",
        "Debate surfaced disagreement on how much risk the user should tolerate upfront.",
    ]
    reservations = [
        "Public-source distillation has uncertainty and should be treated as bounded guidance.",
        "Final route still depends on user constraints not fully specified in the prompt.",
    ]
    route = RouteRecommendation(
        route_name="Balanced Route",
        description="Start with a low-regret path, then branch based on early signal quality.",
        supporters=[member.celebrity_name for member in studio.members[:3]],
        opponents=[member.celebrity_name for member in studio.members[3:5]],
        suitable_when=["User has moderate resource constraints.", "Need both execution and optionality."],
        avoid_when=["User requires immediate high-risk all-in strategy."],
        first_actions=[
            "Collect baseline metrics in 7 days.",
            "Run one pilot with explicit success/failure criteria.",
            "Review with the same studio after first feedback loop.",
        ],
    )
    return SynthesisResult(
        consensus_points=consensus,
        disagreement_points=disagreements + [f"Directed interactions: {len(interaction_msgs)}; convergence notes: {len(convergence_msgs)}."],
        reservation_points=reservations,
        conditional_recommendations=[route],
        final_synthesis=(
            "Use a staged decision route: preserve optionality in step 1, "
            "increase commitment only after evidence quality improves."
        ),
    )


def build_synthesis(
    spec: ScenarioSpec,
    studio: StudioConfig,
    messages: list[Message],
    llm: LLMClient | None,
) -> SynthesisResult:
    if llm is None:
        return _heuristic_synthesis(spec, studio, messages)
    try:
        parsed = llm.complete_json(
            system_prompt=(
                "You are the leader synthesizer in an Open Studio Field collaboration. "
                "Return explicit consensus, disagreement, reservation, and conditional routes."
            ),
            user_prompt=(
                "Return JSON with keys: consensus_points, disagreement_points, reservation_points, "
                "conditional_recommendations, final_synthesis.\n"
                "Each conditional recommendation item needs: route_name, description, supporters, "
                "opponents, suitable_when, avoid_when, first_actions.\n"
                f"scenario={spec.model_dump()}\n"
                f"studio={[m.model_dump() for m in studio.members]}\n"
                f"messages={_message_digest(messages)}"
            ),
        )
        return SynthesisResult(**parsed)
    except Exception:
        return _heuristic_synthesis(spec, studio, messages)
