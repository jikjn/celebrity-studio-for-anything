from __future__ import annotations

from collections import Counter
from pathlib import Path

from celebrity_studio.config import Settings
from celebrity_studio.models import DiscussionConfig, RuntimeConfig
from celebrity_studio.pipeline import run_pipeline


def test_offline_pipeline_runs(tmp_path: Path) -> None:
    settings = Settings.from_env(workspace_root=Path(__file__).resolve().parents[1])
    settings.offline = True
    runtime = RuntimeConfig(strict_online=False, realtime_distill=False)

    result = run_pipeline(
        query="A student from a normal family wants to study finance and needs a practical education roadmap.",
        settings=settings,
        output_root=tmp_path,
        language_hint="en-US",
        runtime=runtime,
    )

    assert result.selection.actual_team_size >= settings.min_agents
    assert "consensus" in result.report_markdown.lower()
    report_path = Path(result.run_dir) / "report.md"
    assert report_path.exists()


def test_default_discussion_turns_are_at_least_five_per_member(tmp_path: Path) -> None:
    settings = Settings.from_env(workspace_root=Path(__file__).resolve().parents[1])
    settings.offline = True
    runtime = RuntimeConfig(strict_online=False, realtime_distill=False)

    result = run_pipeline(
        query="Design a practical personal knowledge system for a graduate student.",
        settings=settings,
        output_root=tmp_path,
        language_hint="en-US",
        runtime=runtime,
    )

    members = {item.celebrity_name for item in result.studio.members}
    counts = Counter(msg.from_agent for msg in result.debate.messages if msg.from_agent in members)
    assert counts
    assert min(counts.values()) >= 5


def test_user_configurable_min_turns_per_member(tmp_path: Path) -> None:
    settings = Settings.from_env(workspace_root=Path(__file__).resolve().parents[1])
    settings.offline = True
    runtime = RuntimeConfig(
        strict_online=False,
        realtime_distill=False,
        discussion=DiscussionConfig(min_turns_per_member=3, turn_length="brief"),
    )

    result = run_pipeline(
        query="Give me a concise but multi-angle launch strategy for a niche app.",
        settings=settings,
        output_root=tmp_path,
        language_hint="en-US",
        runtime=runtime,
    )

    members = {item.celebrity_name for item in result.studio.members}
    counts = Counter(msg.from_agent for msg in result.debate.messages if msg.from_agent in members)
    assert counts
    assert min(counts.values()) >= 3
