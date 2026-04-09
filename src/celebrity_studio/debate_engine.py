from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import json
import re
from typing import Any, Callable

from .agent_runtime import AgentSession, build_leader_system_prompt, build_member_system_prompt
from .models import (
    ChallengeEdge,
    DebateSession,
    DiscussionConfig,
    DistilledSkill,
    Message,
    RouteRecommendation,
    ScenarioSpec,
    StudioConfig,
    SynthesisResult,
    Task,
)
from .providers import ProviderRegistry

OPEN_PHASE = "salon-open"
FLOW_PHASE_PREFIX = "salon-flow"
PULSE_PHASE = "salon-pulse"
SYNTH_PHASE = "salon-synthesis"

FIELD_RULES = [
    "dominance ceiling",
    "silent genius wake-up",
    "dead-thread pruning",
    "resonance amplification",
    "drift boundary",
]

PROCESS_META_HINTS = {"sprint", "workflow", "orchestration", "meeting", "phase", "agent", "pipeline", "gate"}

SALON_META_REWRITE = [
    ("\u6211\u6765\u6536\u655b", "\u6211\u5148\u628a\u5927\u5bb6\u7684\u89c2\u70b9\u805a\u7126\u4e00\u4e0b"),
    ("\u6536\u655b", "\u805a\u7126"),
    ("\u7ebf\u7a0b", "\u8bdd\u9898"),
    ("\u9636\u6bb5", "\u6b64\u523b"),
    ("\u6d41\u7a0b", "\u8ba8\u8bba"),
    ("protocol", "discussion style"),
    ("pipeline", "discussion"),
    ("converge", "focus"),
]

TURN_LENGTH_HINTS = {
    "brief": "Keep each turn short: around 1 compact paragraph.",
    "standard": "Use 1-2 short paragraphs with one clear point and one response to others.",
    "long": "Use 2-3 substantial paragraphs and include explicit challenge/support to other views.",
    "extended": "Use 3-4 substantial paragraphs with concrete examples and multi-angle interaction.",
}

TURN_STYLE_FALLBACK = "像同桌沙龙一样自由交流，允许质疑、支持、反驳、补充，不走模板话术，优先真实观点碰撞。"

VALUE_POINT_TOKENS = {
    "建议",
    "方案",
    "步骤",
    "比例",
    "预算",
    "训练",
    "风险",
    "取舍",
    "优先",
    "约束",
    "hook",
    "副歌",
    "声调",
    "咬字",
    "因为",
    "因此",
    "所以",
    "should",
    "must",
    "risk",
    "tradeoff",
    "ratio",
    "budget",
}

BOILERPLATE_PATTERNS = [
    r"^(我先(?:接|回应|回應|补充|補充|承接|回到|回应一下|回应下|接住|接著|接着)[^，,；;:：]*[，,；;:：]\s*)+",
    r"^(我(?:回应|回應|补充|補充|接著|接着)[^，,；;:：]*[，,；;:：]\s*)+",
]


def _flow_phase(round_no: int) -> str:
    return f"{FLOW_PHASE_PREFIX}-r{round_no:02d}"


def _turn_length_hint(turn_length: str) -> str:
    return TURN_LENGTH_HINTS.get(turn_length, TURN_LENGTH_HINTS["long"])


def _salon_rounds(discussion: DiscussionConfig) -> int:
    # Opening turn counts as one turn per member.
    return max(1, discussion.min_turns_per_member - 1)


def _init_tasks(members: list[str], discussion: DiscussionConfig) -> list[Task]:
    free_rounds = _salon_rounds(discussion)
    owner = ",".join(members) or "studio-members"
    return [
        Task(
            id="task-01",
            owner=owner,
            description="salon-open-kickoff",
            dependencies=[],
            status="todo",
        ),
        Task(
            id="task-02",
            owner=owner,
            description=f"salon-free-dialogue-{free_rounds}-rounds",
            dependencies=["task-01"],
            status="todo",
        ),
        Task(
            id="task-03",
            owner="studio-leader",
            description="salon-final-distillation",
            dependencies=["task-02"],
            status="todo",
        ),
    ]


@dataclass
class _MsgFactory:
    counter: int = 0

    def create(
        self,
        *,
        phase: str,
        round_no: int,
        from_agent: str,
        to_agent: str,
        message_type: str,
        content: str,
        provider_id: str = "",
        refs: list[str] | None = None,
    ) -> Message:
        self.counter += 1
        return Message(
            id=f"msg-{self.counter:04d}",
            phase=phase,
            round_no=round_no,
            from_agent=from_agent,
            to_agent=to_agent,
            type=message_type,  # type: ignore[arg-type]
            content=content.strip(),
            provider_id=provider_id,
            refs=refs or [],
        )


def _skill_map(skills: list[DistilledSkill]) -> dict[str, DistilledSkill]:
    return {skill.identity.name: skill for skill in skills}


def _provider_sequence(registry: ProviderRegistry, count: int) -> list[str]:
    provider_ids = list(registry.providers.keys())
    if not provider_ids:
        raise ValueError("No providers available.")
    if registry.assignment_strategy == "default_only":
        return [registry.default_provider_id for _ in range(count)]
    return [provider_ids[idx % len(provider_ids)] for idx in range(count)]


def _create_sessions(
    spec: ScenarioSpec,
    studio: StudioConfig,
    skills: list[DistilledSkill],
    registry: ProviderRegistry,
) -> tuple[dict[str, AgentSession], AgentSession]:
    skill_by_name = _skill_map(skills)
    provider_ids = _provider_sequence(registry, len(studio.members))
    sessions: dict[str, AgentSession] = {}
    for idx, member in enumerate(studio.members):
        skill = skill_by_name.get(member.celebrity_name)
        if skill is None:
            continue
        member.provider_id = provider_ids[idx]
        provider = registry.get(member.provider_id)
        sessions[member.celebrity_name] = AgentSession(
            member=member,
            provider=provider,
            system_prompt=build_member_system_prompt(member, skill, spec),
            model=provider.model,
            temperature=getattr(provider, "temperature", None),
        )
    leader_provider = registry.leader()
    leader_member = studio.members[0] if studio.members else None
    if leader_member is None:
        from .models import StudioMember

        leader_member = StudioMember(
            agent_id="studio-leader",
            celebrity_name="studio-leader",
            skill_slug="studio-leader",
            role_in_studio="Leader",
            speaking_style="Structured",
            challenge_style="Field orchestration",
            provider_id=registry.default_provider_id,
            session_id="studio-leader-session",
        )
    leader_member.provider_id = registry.leader_provider_id or registry.default_provider_id
    leader_session = AgentSession(
        member=leader_member,
        provider=leader_provider,
        system_prompt=build_leader_system_prompt(spec),
        model=leader_provider.model,
        temperature=getattr(leader_provider, "temperature", None),
    )
    return sessions, leader_session


def _parallel_call(tasks: list[tuple[str, Callable[[], Any]]], max_workers: int | None = None) -> dict[str, Any]:
    if not tasks:
        return {}
    worker_count = max_workers if max_workers is not None else min(8, len(tasks))
    worker_count = max(1, min(worker_count, len(tasks)))
    output: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {executor.submit(fn): key for key, fn in tasks}
        for future in as_completed(future_map):
            key = future_map[future]
            try:
                output[key] = future.result()
            except Exception as exc:
                output[key] = {"_error": str(exc)}
    return output


def _raise_if_generation_collapsed(payloads: dict[str, Any], total_agents: int, stage_name: str) -> None:
    if total_agents <= 0:
        return
    errors = []
    for payload in payloads.values():
        if isinstance(payload, dict) and "_error" in payload:
            errors.append(str(payload["_error"]))
    if not errors:
        return
    # When most agents fail in one stage, continuing will only produce garbage summaries.
    if len(errors) >= max(2, int(total_agents * 0.6)):
        sample = errors[0][:220]
        raise RuntimeError(
            f"Generation collapsed at {stage_name}: {len(errors)}/{total_agents} agent calls failed. "
            f"Sample error: {sample}. "
            "Likely provider availability issue (network disconnect, request timeout, or usage/quota limit)."
        )


def _compact_message_view(messages: list[Message], limit: int = 20) -> list[dict[str, Any]]:
    return [
        {"id": m.id, "phase": m.phase, "from": m.from_agent, "to": m.to_agent, "content": m.content, "refs": m.refs}
        for m in messages[-limit:]
    ]


def _problem_field(spec: ScenarioSpec) -> dict[str, Any]:
    tensions = ["short-term feasibility vs long-term value", "novelty vs user-fit robustness"]
    tags = {tag.lower() for tag in spec.domain_tags}
    if "music" in tags:
        tensions = ["style coherence vs memorability", "cultural authenticity vs trend aesthetics"]
    return {
        "north_star": spec.raw_user_query,
        "hidden_tensions": tensions,
        "success_feel": ["direct task answer", "clear assumptions", "executable next steps"],
    }


def _safe_slug(value: str) -> str:
    text = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    return "-".join(part for part in text.split("-") if part)[:48] or "general-thread"


def _naturalize_salon_text(text: str) -> str:
    cleaned = (text or "").strip()
    for src, dst in SALON_META_REWRITE:
        cleaned = cleaned.replace(src, dst)
    cleaned = re.sub(r"\b([A-Z][A-Za-z.\- ]{1,30}),\s*check whether\b", r"Can I ask \1 whether", cleaned)
    cleaned = re.sub(r"\b([A-Z][A-Za-z.\- ]{1,30}),\s*price the downside\b", r"I want \1's view on the downside if", cleaned)
    cleaned = re.sub(r"^\s*check whether\b", "I would look at whether", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bprice the downside\b", "estimate the downside", cleaned, flags=re.IGNORECASE)
    for pattern in BOILERPLATE_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned).strip()
    return cleaned


def _as_dialogue_line(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return "；".join(parts)
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            key_text = str(key).strip()
            item_text = _as_dialogue_line(item)
            if not item_text:
                continue
            parts.append(f"{key_text}: {item_text}")
        return "；".join(parts)
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _extract_resonance_targets(raw: Any) -> list[str]:
    if raw is None:
        return []
    items = raw if isinstance(raw, (list, tuple, set)) else [raw]
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        name = str(item).strip()
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out[:4]


def _stage_open_room(
    spec: ScenarioSpec,
    sessions: dict[str, AgentSession],
    field: dict[str, Any],
    discussion: DiscussionConfig,
) -> dict[str, Any]:
    tasks: list[tuple[str, Callable[[], Any]]] = []
    style = discussion.interaction_style or TURN_STYLE_FALLBACK
    length_hint = _turn_length_hint(discussion.turn_length)
    serial_mode = any(type(session.provider).__name__ == "CodexCliProvider" for session in sessions.values())
    for _name, session in sessions.items():
        prompt = (
            "Open Studio Field kickoff.\n"
            f"Problem field: {field}\nScenario: {spec.raw_user_query}\n"
            f"User interaction style preference: {style}\n"
            f"Turn-length guidance: {length_hint}\n"
            "Speak like a person at the same table. Mention one concrete viewpoint and invite another member to respond.\n"
            "You may challenge or support earlier assumptions. Do not use workflow narration.\n"
            "Avoid turn-taking boilerplate like '我先接.../我回应...' and speak directly in natural daily language.\n"
            "Avoid process words: phase, stage, thread, converge, protocol, gate, pipeline, 收敛, 线程, 阶段, 流程.\n"
            "Return JSON keys: opening_statement, proposed_thread, to_agent(optional), resonance_targets(list)."
        )
        tasks.append((session.member.celebrity_name, lambda s=session, p=prompt: s.ask_json(p, store=True)))
    return _parallel_call(tasks, max_workers=1 if serial_mode else None)


def _stage_breathe(
    sessions: dict[str, AgentSession],
    field: dict[str, Any],
    recent_messages: list[Message],
    round_no: int,
    discussion: DiscussionConfig,
) -> dict[str, Any]:
    counts = Counter(m.from_agent for m in recent_messages if m.from_agent in sessions)
    avg = (sum(counts.values()) / len(sessions)) if sessions else 0.0
    tasks: list[tuple[str, Callable[[], Any]]] = []
    trace = _compact_message_view(recent_messages, limit=20)
    style = discussion.interaction_style or TURN_STYLE_FALLBACK
    length_hint = _turn_length_hint(discussion.turn_length)
    serial_mode = any(type(session.provider).__name__ == "CodexCliProvider" for session in sessions.values())
    for _name, session in sessions.items():
        speaker = session.member.celebrity_name
        nudge = "Respond naturally to another person's point, then add your own concrete view."
        if counts.get(speaker, 0) > avg + 0.8:
            nudge = "You already spoke a lot; still be substantial but leave room for others."
        elif counts.get(speaker, 0) < avg - 0.8:
            nudge = "You are underrepresented; push one strong perspective and pick one person to engage."
        prompt = (
            f"Free salon round {round_no}.\n"
            f"Problem field: {field}\nTrace: {trace}\nField rules: {FIELD_RULES}\n"
            f"User interaction style preference: {style}\n"
            f"Turn-length guidance: {length_hint}\n"
            f"Nudge: {nudge}\n"
            "Speak as table conversation, not command dispatch.\n"
            "Allowed interaction moves: challenge, support, question, build_on, new_thread, synthesize.\n"
            "Avoid turn-taking boilerplate like '我先接.../我回应...' and write direct natural speech.\n"
            "Do not issue task-manager style orders like 'X, go check ...'.\n"
            "Avoid process words: phase, stage, thread, converge, protocol, gate, pipeline, 收敛, 线程, 阶段, 流程.\n"
            "Return JSON keys: action, to_agent, thread, content, drift_value, resonance_targets(list)."
        )
        tasks.append((speaker, lambda s=session, p=prompt: s.ask_json(p, store=True)))
    return _parallel_call(tasks, max_workers=1 if serial_mode else None)


def _derive_centers(messages: list[Message]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Message]] = defaultdict(list)
    for msg in messages:
        if msg.type == "synthesis":
            continue
        thread = next((ref.split(":", 1)[1] for ref in msg.refs if ref.startswith("thread:")), "general-thread")
        grouped[thread].append(msg)
    centers: list[dict[str, Any]] = []
    for thread, items in grouped.items():
        if len(items) < 2:
            continue
        centers.append(
            {
                "center": thread,
                "signal_strength": len(items),
                "participants": sorted({item.from_agent for item in items}),
            }
        )
    centers.sort(key=lambda item: item["signal_strength"], reverse=True)
    return centers


def _leader_room_pulse(
    leader: AgentSession,
    field: dict[str, Any],
    centers: list[dict[str, Any]],
    recent_messages: list[Message],
    round_no: int,
    discussion: DiscussionConfig,
) -> str:
    style = discussion.interaction_style or TURN_STYLE_FALLBACK
    prompt = (
        f"Host pulse during free salon round {round_no}.\n"
        f"Problem field: {field}\nCenters: {centers}\n"
        f"Trace: {_compact_message_view(recent_messages, limit=18)}\n"
        f"User interaction style preference: {style}\n"
        "Give one short paragraph: keep strong viewpoints alive, point out one unresolved tension, and invite direct response.\n"
        "Avoid turn-taking boilerplate like '我先接.../我回应...'.\n"
        "Do not use workflow narration or procedural stage words."
    )
    try:
        text = leader.ask_text(prompt, store=True)
    except Exception as exc:
        text = f"Host pulse fallback: keep tension visible and continue direct argument exchange. ({exc})"
    return _naturalize_salon_text(text)


def _looks_process_only_answer(text: str) -> bool:
    lowered = text.lower()
    if not lowered.strip():
        return True
    hint_hits = sum(1 for token in PROCESS_META_HINTS if token in lowered)
    task_hits = sum(1 for token in ("choose", "build", "launch", "study", "write", "compose", "ship", "deliver") if token in lowered)
    return hint_hits >= 3 and task_hits == 0


def _is_song_creation_scenario(spec: ScenarioSpec) -> bool:
    lowered = spec.raw_user_query.lower()
    tags = {tag.lower() for tag in spec.domain_tags}
    if "music" in tags or "songwriting" in tags or "cantopop" in tags:
        return True
    return any(token in lowered for token in ("song", "music", "lyrics", "cantopop", "cantonese", "粤语", "歌曲", "作词", "作曲", "编曲"))


def _has_song_artifact_sections(answer: str) -> bool:
    lowered = answer.lower()
    markers = ("歌名", "意象池", "比例", "创作指令", "title direction", "imagery pool", "style ratio", "production brief")
    return sum(1 for marker in markers if marker in lowered) >= 2


def _song_artifact_answer(spec: ScenarioSpec, routes: list[RouteRecommendation]) -> str:
    route_line = routes[0].description if routes else "先用可传唱的粤语 hook 立住，再在第二轮推进赛博冲突升级。"
    return (
        "最终创作建议（可直接落地）\n"
        "1) 歌名方向（示例）\n"
        "- 《电子望月》 《九龙招魂》 《义体南音》\n"
        "2) 风格比例建议\n"
        "- 40% 粤语都市情绪\n"
        "- 25% 中国古典意象\n"
        "- 25% 赛博朋克世界设定\n"
        "- 10% 可复唱 hook\n"
        "3) 意象池（分组）\n"
        "- 中国风: 月、宫灯、祖庙、夜雨\n"
        "- 赛博: 义体、接口、云端、霓虹\n"
        "- 粤语都市: 天桥、旧楼、街灯、末班车\n"
        "4) 第一版创作指令\n"
        f"- 任务: {spec.raw_user_query}\n"
        f"- 路线: {route_line}\n"
        "- 约束: 不能做素材拼贴；必须让‘人情旧梦’与‘技术异化’在歌词和声场都发生冲突。\n"
    )


def _strip_boilerplate_prefix(text: str) -> str:
    cleaned = (text or "").strip()
    previous = None
    while cleaned and cleaned != previous:
        previous = cleaned
        for pattern in BOILERPLATE_PATTERNS:
            cleaned = re.sub(pattern, "", cleaned).strip()
    return cleaned


def _point_value_score(text: str) -> float:
    sentence = _strip_boilerplate_prefix((text or "").strip())
    if not sentence:
        return -999.0
    lowered = sentence.lower()
    score = float(len(sentence))
    if any(ch.isdigit() for ch in sentence):
        score += 24.0
    token_hits = sum(1 for token in VALUE_POINT_TOKENS if token in lowered)
    score += min(6, token_hits) * 10.0
    if any(token in lowered for token in ("支持", "挑战", "反对", "不同意", "同意", "保留", "坚持", "建议")):
        score += 12.0
    if any(token in lowered for token in ("我先接", "我回应", "回应主持人", "也回应")) and token_hits == 0:
        score -= 45.0
    if len(sentence) < 10:
        score -= 30.0
    return score


def _extract_value_points(text: str, max_points: int = 3) -> list[str]:
    compact = re.sub(r"\s+", " ", (text or "").strip())
    if not compact:
        return []
    chunks = [item.strip() for item in re.split(r"[。!?！？\n]+", compact) if item.strip()]
    candidates: list[tuple[float, str]] = []
    for chunk in chunks:
        for part in re.split(r"[；;]", chunk):
            sentence = _strip_boilerplate_prefix(part.strip(" ，,;；:："))
            if not sentence:
                continue
            score = _point_value_score(sentence)
            if score < 18.0:
                continue
            candidates.append((score, sentence))
    if not candidates:
        fallback = _strip_boilerplate_prefix(compact)
        if fallback:
            return [fallback[:170].rstrip("，,;； ") + ("..." if len(fallback) > 170 else "")]
        return []
    candidates.sort(key=lambda item: item[0], reverse=True)
    out: list[str] = []
    seen: set[str] = set()
    for _score, sentence in candidates:
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        trimmed = sentence[:170].rstrip("，,;； ") + ("..." if len(sentence) > 170 else "")
        out.append(trimmed)
        if len(out) >= max_points:
            break
    return out


def _message_detail_score(msg: Message) -> float:
    text = (msg.content or "").strip()
    if not text:
        return -999.0
    lowered = text.lower()
    score = float(len(text))
    if any(ch.isdigit() for ch in text):
        score += 18.0
    if any(token in lowered for token in VALUE_POINT_TOKENS):
        score += 26.0
    if msg.type in {"challenge", "defense", "revision"}:
        score += 12.0
    if any(token in lowered for token in ("fallback", "generation error", "adds one strong reaction")):
        score -= 45.0
    candidates = _extract_value_points(text, max_points=2)
    if candidates:
        score += max(_point_value_score(item) for item in candidates) * 0.35
    return score


def _build_agent_detail_section(messages: list[Message], members: list[str]) -> str:
    if not members:
        return ""
    lines = ["各 Agent 关键观点汇总（按讨论原文提炼）"]
    added = 0
    for member in members:
        pool = [msg for msg in messages if msg.from_agent == member and msg.type != "synthesis" and (msg.content or "").strip()]
        if not pool:
            continue
        ranked = sorted(pool, key=lambda msg: (_message_detail_score(msg), msg.round_no), reverse=True)
        candidate_points: list[tuple[float, str]] = []
        for msg in ranked[:8]:
            for point in _extract_value_points(msg.content, max_points=3):
                score = _point_value_score(point) + (_message_detail_score(msg) * 0.15)
                candidate_points.append((score, point))
        candidate_points.sort(key=lambda item: item[0], reverse=True)

        points: list[str] = []
        seen: set[str] = set()
        for _score, point in candidate_points:
            key = point.lower()
            if key in seen:
                continue
            seen.add(key)
            points.append(point)
            if len(points) >= 2:
                break
        if not points:
            continue
        lines.append(f"- {member}: {'；'.join(points)}")
        added += 1
    if added == 0:
        return ""
    return "\n".join(lines)


def _augment_with_agent_details(answer: str, messages: list[Message], members: list[str]) -> str:
    base = (answer or "").strip()
    detail = _build_agent_detail_section(messages, members)
    if not detail:
        return base
    if "各 Agent 关键观点汇总" in base:
        return base
    structured_hits = 0
    for member in members:
        if not member:
            continue
        if re.search(rf"(^|\n)-\s*{re.escape(member)}\s*:", base):
            structured_hits += 1
    if structured_hits >= max(2, len(members) // 2):
        return base
    if base:
        return f"{base}\n\n{detail}"
    return detail


def _ensure_task_answer(spec: ScenarioSpec, answer: str, routes: list[RouteRecommendation]) -> str:
    if _is_song_creation_scenario(spec) and not _has_song_artifact_sections(answer):
        artifact = _song_artifact_answer(spec, routes)
        cleaned = answer.strip()
        if cleaned and not _looks_process_only_answer(cleaned) and "task answer fallback" not in cleaned.lower():
            return f"{cleaned}\n\n{artifact}"
        return artifact
    lowered = answer.strip().lower()
    if answer.strip() and not _looks_process_only_answer(answer) and "task answer fallback" not in lowered:
        return answer.strip()
    primary = routes[0] if routes else None
    if primary is None:
        return (
            f"For the task '{spec.raw_user_query}', pick one high-fit route now and execute a small reversible first step "
            "within 7 days, then expand only after evidence confirms user-fit."
        )
    first_actions = "; ".join(primary.first_actions[:3]) or "Define one concrete first step and run it this week."
    return (
        f"For the task '{spec.raw_user_query}', choose route '{primary.route_name}'. "
        f"Reason: {primary.description}. Start now with: {first_actions}."
    )


def _leader_final_synthesis(
    leader: AgentSession,
    spec: ScenarioSpec,
    studio: StudioConfig,
    messages: list[Message],
    discussion: DiscussionConfig,
) -> SynthesisResult:
    style = discussion.interaction_style or TURN_STYLE_FALLBACK
    length_hint = _turn_length_hint(discussion.turn_length)
    prompt = (
        "Studio final distillation after free salon dialogue.\n"
        f"Scenario: {spec.raw_user_query}\nMembers: {[m.model_dump() for m in studio.members]}\n"
        f"Trace: {_compact_message_view(messages, limit=48)}\n"
        f"User interaction style preference: {style}\n"
        f"Turn-length guidance used in discussion: {length_hint}\n"
        "Speak as a host inside the room, not a workflow bot.\n"
        "In final_synthesis, include concrete and attributable viewpoints from each agent.\n"
        "Avoid only giving abstract ratios/checklists without who-said-what details.\n"
        "Avoid summarizing with turn-taking boilerplate (for example: '我先接主持人的问题...').\n"
        "Return JSON keys: consensus_points, disagreement_points, reservation_points, conditional_recommendations, final_synthesis."
    )
    members = [member.celebrity_name for member in studio.members]
    try:
        parsed = leader.ask_json(prompt, store=True)
        synthesis = SynthesisResult(**parsed)
        final_text = _ensure_task_answer(spec, synthesis.final_synthesis, synthesis.conditional_recommendations)
        final_text = _augment_with_agent_details(final_text, messages, members)
        synthesis.final_synthesis = _naturalize_salon_text(final_text)
        return synthesis
    except Exception:
        fallback = SynthesisResult(
            consensus_points=["Free-salon interaction surfaced multiple actionable viewpoints."],
            disagreement_points=["Risk appetite and style density remained contested."],
            reservation_points=["Additional user constraints are still needed."],
            conditional_recommendations=[
                RouteRecommendation(
                    route_name="Balanced Route",
                    description="Start with a constrained pilot and scale only after signal quality improves.",
                    supporters=[m.celebrity_name for m in studio.members[:3]],
                    opponents=[m.celebrity_name for m in studio.members[3:5]],
                    suitable_when=["Need both creativity and execution reliability."],
                    avoid_when=["User prefers immediate all-in experimentation."],
                    first_actions=[
                        "Write one concrete output brief matching the user task.",
                        "Produce a minimal viable draft and test with target users.",
                        "Revise only the weakest assumption after feedback.",
                    ],
                )
            ],
            final_synthesis=f"Task answer fallback for '{spec.raw_user_query}': choose a balanced route with bounded risk.",
        )
        final_text = _ensure_task_answer(spec, fallback.final_synthesis, fallback.conditional_recommendations)
        final_text = _augment_with_agent_details(final_text, messages, members)
        fallback.final_synthesis = _naturalize_salon_text(final_text)
        return fallback


def _build_challenge_edges(messages: list[Message]) -> list[ChallengeEdge]:
    latest_by_edge: dict[tuple[str, str], Message] = {}
    counts: Counter[tuple[str, str]] = Counter()
    for msg in messages:
        if msg.to_agent and msg.to_agent != "all":
            key = (msg.from_agent, msg.to_agent)
            counts[key] += 1
            latest_by_edge[key] = msg
        for ref in msg.refs:
            if not ref.startswith("resonance:"):
                continue
            target = ref.split(":", 1)[1].strip()
            if not target or target == msg.from_agent:
                continue
            key = (msg.from_agent, target)
            counts[key] += 1
            latest_by_edge[key] = msg
    return [
        ChallengeEdge(source=src, target=dst, count=count, latest_message_id=latest_by_edge[(src, dst)].id)
        for (src, dst), count in counts.items()
    ]


def _offline_debate(spec: ScenarioSpec, studio: StudioConfig, discussion: DiscussionConfig) -> DebateSession:
    factory = _MsgFactory()
    member_names = [m.celebrity_name for m in studio.members]
    session = DebateSession(
        studio_id=spec.scenario_id,
        tasks=_init_tasks(member_names, discussion),
        messages=[],
        rounds_completed=0,
    )
    free_rounds = _salon_rounds(discussion)
    stance_cycle = ["challenge", "support", "question", "build_on", "synthesize"]

    session.tasks[0].status = "doing"
    for idx, name in enumerate(member_names):
        target = member_names[(idx + 1) % len(member_names)] if len(member_names) > 1 else "all"
        refs = ["thread:problem-field", "action:open"]
        if target != "all":
            refs.append(f"resonance:{target}")
        session.messages.append(
            factory.create(
                phase=OPEN_PHASE,
                round_no=1,
                from_agent=name,
                to_agent=target if target != name else "all",
                message_type="claim",
                refs=refs,
                content=f"{name} 抛出一个核心判断，并邀请 {target} 直接回应这个判断。",
            )
        )
    session.tasks[0].status = "done"
    session.rounds_completed = 1

    session.tasks[1].status = "doing"
    for offset in range(free_rounds):
        round_no = 2 + offset
        for idx, name in enumerate(member_names):
            target = member_names[(idx + offset + 1) % len(member_names)] if len(member_names) > 1 else "all"
            action = stance_cycle[(idx + offset) % len(stance_cycle)]
            msg_type = {
                "challenge": "challenge",
                "question": "challenge",
                "support": "defense",
                "synthesize": "revision",
                "build_on": "note",
            }.get(action, "note")
            refs = [
                "thread:primary-direction",
                f"action:{action}",
                f"drift:{0.28 + (0.02 * (idx % 3)):.2f}",
            ]
            if target != "all":
                refs.append(f"resonance:{target}")
            session.messages.append(
                factory.create(
                    phase=_flow_phase(round_no),
                    round_no=round_no,
                    from_agent=name,
                    to_agent=target if target != name else "all",
                    message_type=msg_type,
                    refs=refs,
                    content=f"{name} 基于上一轮观点做 {action}，并把问题抛给 {target}。",
                )
            )
        if round_no % 2 == 0 and offset < free_rounds - 1:
            centers = _derive_centers(session.messages)
            session.messages.append(
                factory.create(
                    phase=PULSE_PHASE,
                    round_no=round_no,
                    from_agent="studio-leader",
                    to_agent="all",
                    message_type="synthesis",
                    refs=[f"centers:{len(centers)}"],
                    content="主持人提醒：保留分歧，不要变成轮流陈述，请继续彼此回应。",
                )
            )
    session.tasks[1].status = "done"
    session.rounds_completed = 1 + free_rounds

    route = RouteRecommendation(
        route_name="Offline Free-Salon Route",
        description="持续挑战与支持并行推进，最后收束到可执行方案。",
        supporters=member_names[:3],
        opponents=member_names[3:5],
        suitable_when=["Need broad ideation with direct interaction."],
        avoid_when=["Need deterministic one-shot output only."],
        first_actions=["列出一版可执行方案", "选一个低风险切口先验证", "根据反馈迭代第二版"],
    )
    final_text = _ensure_task_answer(
        spec,
        f"Task answer for '{spec.raw_user_query}': keep free-salon dialogue alive and distill into one concrete route.",
        [route],
    )
    final_text = _augment_with_agent_details(final_text, session.messages, member_names)
    session.synthesis = SynthesisResult(
        consensus_points=["Free-salon exchange kept multiple viewpoints active."],
        disagreement_points=["Execution speed vs artistic/strategic purity remained contested."],
        reservation_points=["More explicit user constraints can still change route order."],
        conditional_recommendations=[route],
        final_synthesis=final_text,
    )

    session.tasks[2].status = "doing"
    final_round = 2 + free_rounds
    session.messages.append(
        factory.create(
            phase=SYNTH_PHASE,
            round_no=final_round,
            from_agent="studio-leader",
            to_agent="all",
            message_type="synthesis",
            content=_naturalize_salon_text(session.synthesis.final_synthesis),
        )
    )
    session.tasks[2].status = "done"
    session.rounds_completed = final_round
    session.challenge_edges = _build_challenge_edges(session.messages)
    return session


def run_debate(
    spec: ScenarioSpec,
    studio: StudioConfig,
    skills: list[DistilledSkill],
    registry: ProviderRegistry | None,
    discussion: DiscussionConfig | None = None,
) -> DebateSession:
    discussion = discussion or DiscussionConfig()
    if registry is None:
        return _offline_debate(spec, studio, discussion)

    field = _problem_field(spec)
    free_rounds = _salon_rounds(discussion)
    member_names = [m.celebrity_name for m in studio.members]
    session = DebateSession(
        studio_id=spec.scenario_id,
        tasks=_init_tasks(member_names, discussion),
        messages=[],
        rounds_completed=0,
    )
    member_sessions, leader_session = _create_sessions(spec, studio, skills, registry)
    factory = _MsgFactory()

    session.tasks[0].status = "doing"
    opening = _stage_open_room(spec, member_sessions, field, discussion)
    _raise_if_generation_collapsed(opening, len(member_sessions), "salon-open")
    for name, payload in opening.items():
        to_agent = "all"
        refs = ["action:open"]
        if isinstance(payload, dict) and "_error" in payload:
            content = _naturalize_salon_text(f"Open-room generation error: {payload['_error']}")
            thread = "problem-field"
        else:
            content = _naturalize_salon_text(str(payload.get("opening_statement", str(payload))))
            thread = _safe_slug(str(payload.get("proposed_thread", "problem-field")))
            target_raw = str(payload.get("to_agent", "all")).strip()
            if target_raw and target_raw in member_sessions and target_raw != name:
                to_agent = target_raw
            refs.extend(f"resonance:{target}" for target in _extract_resonance_targets(payload.get("resonance_targets", [])))
        refs.append(f"thread:{thread}")
        session.messages.append(
            factory.create(
                phase=OPEN_PHASE,
                round_no=1,
                from_agent=name,
                to_agent=to_agent,
                message_type="claim",
                content=content,
                refs=refs,
                provider_id=member_sessions[name].member.provider_id,
            )
        )
    session.tasks[0].status = "done"
    session.rounds_completed = 1

    session.tasks[1].status = "doing"
    for offset in range(free_rounds):
        round_no = 2 + offset
        payloads = _stage_breathe(member_sessions, field, session.messages, round_no, discussion)
        _raise_if_generation_collapsed(payloads, len(member_sessions), f"salon-flow-r{round_no:02d}")
        for name, payload in payloads.items():
            if isinstance(payload, dict) and "_error" in payload:
                action = "build_on"
                to_agent = "all"
                thread = "fallback-thread"
                content = _naturalize_salon_text(f"Salon turn error: {payload['_error']}")
                refs = [f"thread:{thread}", f"action:{action}", "drift:0.40"]
            else:
                action = str(payload.get("action", "build_on")).strip().lower()
                if action not in {"new_thread", "build_on", "question", "challenge", "support", "synthesize"}:
                    action = "build_on"
                to_agent = str(payload.get("to_agent", "all")).strip() or "all"
                if to_agent not in member_sessions or to_agent == name:
                    to_agent = "all"
                thread = _safe_slug(str(payload.get("thread", "general-thread")))
                content = _naturalize_salon_text(
                    _as_dialogue_line(payload.get("content", "")).strip() or f"{name} adds one strong reaction."
                )
                try:
                    drift = max(0.0, min(1.0, float(payload.get("drift_value", 0.35))))
                except Exception:
                    drift = 0.35
                refs = [f"thread:{thread}", f"action:{action}", f"drift:{drift:.2f}"]
                refs.extend(
                    f"resonance:{target}"
                    for target in _extract_resonance_targets(payload.get("resonance_targets", []))
                    if target != name
                )
            message_type = {
                "new_thread": "claim",
                "challenge": "challenge",
                "question": "challenge",
                "support": "defense",
                "synthesize": "revision",
                "build_on": "note",
            }.get(action, "note")
            session.messages.append(
                factory.create(
                    phase=_flow_phase(round_no),
                    round_no=round_no,
                    from_agent=name,
                    to_agent=to_agent,
                    message_type=message_type,
                    content=content,
                    refs=refs,
                    provider_id=member_sessions[name].member.provider_id,
                )
            )
        if round_no % 2 == 0 and offset < free_rounds - 1:
            centers = _derive_centers(session.messages)
            pulse_text = _leader_room_pulse(leader_session, field, centers, session.messages, round_no, discussion)
            session.messages.append(
                factory.create(
                    phase=PULSE_PHASE,
                    round_no=round_no,
                    from_agent="studio-leader",
                    to_agent="all",
                    message_type="synthesis",
                    content=pulse_text,
                    refs=[f"centers:{len(centers)}"],
                    provider_id=leader_session.member.provider_id,
                )
            )
    session.tasks[1].status = "done"
    session.rounds_completed = 1 + free_rounds

    session.tasks[2].status = "doing"
    synthesis = _leader_final_synthesis(leader_session, spec, studio, session.messages, discussion)
    final_round = 2 + free_rounds
    session.messages.append(
        factory.create(
            phase=SYNTH_PHASE,
            round_no=final_round,
            from_agent="studio-leader",
            to_agent="all",
            message_type="synthesis",
            content=_naturalize_salon_text(synthesis.final_synthesis),
            provider_id=leader_session.member.provider_id,
        )
    )
    session.synthesis = synthesis
    session.tasks[2].status = "done"
    session.rounds_completed = final_round
    session.challenge_edges = _build_challenge_edges(session.messages)
    return session
