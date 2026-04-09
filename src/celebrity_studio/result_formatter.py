from __future__ import annotations

from collections import defaultdict

from .models import DebateSession, DistilledSkill, ScenarioSpec, SelectionResult, StudioConfig


def _selection_table(selection: SelectionResult) -> str:
    header = "| Name | Fit | Anti-fit | Final | Why selected |\n|---|---:|---:|---:|---|\n"
    rows = []
    for item in selection.selected:
        rows.append(
            f"| {item.name} | {item.fit_score:.2f} | {item.anti_fit_penalty:.2f} | {item.final_score:.2f} | "
            f"{'; '.join(item.fit_reasons[:2]) or 'N/A'} |"
        )
    return header + "\n".join(rows)


def _rejected_table(selection: SelectionResult) -> str:
    header = "| Name | Anti-fit reasons |\n|---|---|\n"
    rows = []
    for item in selection.rejected[:12]:
        reason = "; ".join(item.anti_fit_reasons[:2]) or "Lower thematic fit / complementarity."
        rows.append(f"| {item.name} | {reason} |")
    return header + "\n".join(rows)


def _members_table(studio: StudioConfig) -> str:
    header = "| Agent | Role | Speaking style | Challenge style | Provider | Session |\n|---|---|---|---|---|---|\n"
    rows = [
        (
            f"| {m.celebrity_name} | {m.role_in_studio} | {m.speaking_style} | {m.challenge_style} | "
            f"{m.provider_id} | {m.session_id} |"
        )
        for m in studio.members
    ]
    return header + "\n".join(rows)


def _discussion_trace(debate: DebateSession) -> str:
    grouped = defaultdict(list)
    for msg in debate.messages:
        grouped[msg.phase].append(msg)
    lines: list[str] = []
    for phase in sorted(grouped.keys()):
        lines.append(f"### {phase}")
        for msg in grouped[phase]:
            prefix = f"[{msg.from_agent} -> {msg.to_agent}]"
            lines.append(f"- {prefix} ({msg.type}) {msg.content}")
        lines.append("")
    return "\n".join(lines)


def _recommendation_section(debate: DebateSession) -> str:
    lines: list[str] = []
    for idx, route in enumerate(debate.synthesis.conditional_recommendations, start=1):
        lines.append(f"### Route {idx}: {route.route_name}")
        lines.append(f"- Description: {route.description}")
        lines.append(f"- Supporters: {', '.join(route.supporters) or 'N/A'}")
        lines.append(f"- Opponents: {', '.join(route.opponents) or 'N/A'}")
        lines.append(f"- Suitable when: {'; '.join(route.suitable_when) or 'N/A'}")
        lines.append(f"- Avoid when: {'; '.join(route.avoid_when) or 'N/A'}")
        lines.append(f"- First actions: {'; '.join(route.first_actions) or 'N/A'}")
        lines.append("")
    return "\n".join(lines)


def _why_these_celebrities(selection: SelectionResult, studio: StudioConfig) -> str:
    member_role = {member.celebrity_name: member.role_in_studio for member in studio.members}
    lines: list[str] = []
    for item in selection.selected:
        role = member_role.get(item.name, "N/A")
        why = "; ".join(item.fit_reasons[:3]) or "Selected for cognitive coverage contribution."
        lines.append(f"- {item.name}: role={role}; reason={why}")
    return "\n".join(lines) or "- No selected celebrities."


def _framing_shifts(debate: DebateSession) -> str:
    phase1 = [
        msg
        for msg in debate.messages
        if msg.phase == "stage-a-open-room" or msg.phase.startswith("salon-open")
    ]
    if not phase1:
        return "- No framing-shift records."
    lines = [f"- {msg.from_agent}: {msg.content}" for msg in phase1]
    return "\n".join(lines)


def _conditional_best_path(debate: DebateSession) -> str:
    routes = debate.synthesis.conditional_recommendations
    if not routes:
        return "- No route available."
    primary = routes[0]
    return (
        f"- Best path (current): {primary.route_name}\n"
        f"- Why: {primary.description}\n"
        f"- Suitable when: {'; '.join(primary.suitable_when) or 'N/A'}\n"
        f"- Avoid when: {'; '.join(primary.avoid_when) or 'N/A'}"
    )


def _skill_paths(skills: list[DistilledSkill]) -> str:
    lines = []
    for skill in skills:
        lines.append(f"- `{skill.slug}`: `data/celebrities/distilled_skills/{skill.slug}/SKILL.md`")
    return "\n".join(lines)


def render_markdown_report(
    scenario: ScenarioSpec,
    selection: SelectionResult,
    studio: StudioConfig,
    debate: DebateSession,
    skills: list[DistilledSkill],
) -> str:
    challenge_edges = "\n".join(
        f"- {edge.source} -> {edge.target}: {edge.count}"
        for edge in sorted(debate.challenge_edges, key=lambda x: (x.source, x.target))
    ) or "- None"

    return (
        f"# MindForge Studio Report - {scenario.scenario_id}\n\n"
        "## Scenario Profile\n"
        f"- Query: {scenario.raw_user_query}\n"
        f"- Language: {scenario.language}\n"
        f"- Domain tags: {', '.join(scenario.domain_tags)}\n"
        f"- Task types: {', '.join(scenario.task_types)}\n"
        f"- Evaluation axes: {', '.join(scenario.evaluation_axes)}\n"
        f"- Parser summary: {scenario.reasoning_summary}\n\n"
        "## Dynamic Selection\n"
        f"{_selection_table(selection)}\n\n"
        "## Rejected Candidates (Anti-fit)\n"
        f"{_rejected_table(selection)}\n\n"
        "## Studio Members and Roles\n"
        f"{_members_table(studio)}\n\n"
        "## Layer 1: Why These Celebrities\n"
        f"{_why_these_celebrities(selection, studio)}\n\n"
        "## Layer 2: Problem Framing Shifts\n"
        f"{_framing_shifts(debate)}\n\n"
        "## Interaction/Resonance Graph (Edge Weights)\n"
        f"{challenge_edges}\n\n"
        "## Debate Trace\n"
        f"{_discussion_trace(debate)}\n"
        "## Layer 3: Consensus\n"
        + "\n".join(f"- {point}" for point in debate.synthesis.consensus_points)
        + "\n\n"
        + "## Layer 4: Unresolved Tensions\n"
        + "\n".join(f"- {point}" for point in debate.synthesis.disagreement_points)
        + "\n\n"
        + "\n".join(f"- {point}" for point in debate.synthesis.reservation_points)
        + "\n\n"
        + "## Layer 5: Action Routes\n"
        + _recommendation_section(debate)
        + "\n"
        + "## Layer 6: Conditional Best Path\n"
        + _conditional_best_path(debate)
        + "\n\n"
        + "## Final Task Answer\n"
        + debate.synthesis.final_synthesis
        + "\n\n"
        + "## Appendix: Skill Card Paths\n"
        + _skill_paths(skills)
        + "\n"
    )
