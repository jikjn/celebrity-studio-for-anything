from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .config import Settings
from .models import DiscussionConfig, ProviderConfig, RuntimeConfig
from .pipeline import run_pipeline

app = typer.Typer(help="MindForge Studio")
console = Console()


def _runtime_from_options(
    *,
    provider_json: str,
    provider_type: str,
    provider_base_url: str,
    provider_model: str,
    provider_key: str,
    provider_timeout_s: int,
    strict_online: bool,
    realtime_distill: bool,
    min_turns_per_member: int,
    turn_length: str,
    interaction_style: str,
) -> RuntimeConfig:
    discussion_patch: dict[str, object] = {}
    if min_turns_per_member > 0:
        discussion_patch["min_turns_per_member"] = min_turns_per_member
    if turn_length.strip():
        discussion_patch["turn_length"] = turn_length.strip()
    if interaction_style.strip():
        discussion_patch["interaction_style"] = interaction_style.strip()

    if provider_json:
        payload = json.loads(Path(provider_json).read_text(encoding="utf-8"))
        runtime = RuntimeConfig(**payload)
    else:
        providers: list[ProviderConfig] = []
        use_provider = bool(provider_key.strip()) or provider_type == "codex_cli"
        if use_provider:
            providers.append(
                ProviderConfig(
                    provider_id="default",
                    provider_type=provider_type,  # type: ignore[arg-type]
                    model=provider_model,
                    api_key=provider_key,
                    base_url=provider_base_url,
                    timeout_s=provider_timeout_s if provider_timeout_s > 0 else (300 if provider_type == "codex_cli" else 120),
                )
            )
        runtime = RuntimeConfig(
            providers=providers,
            default_provider_id="default",
            leader_provider_id="default",
            assignment_strategy="round_robin",
            realtime_distill=realtime_distill,
            strict_online=strict_online,
        )

    if discussion_patch:
        merged = runtime.discussion.model_dump()
        merged.update(discussion_patch)
        runtime = runtime.model_copy(update={"discussion": DiscussionConfig(**merged)})
    return runtime


@app.command("run")
def run_command(
    query: str = typer.Option(..., "--query", "-q", help="User scenario query."),
    team_size: int = typer.Option(0, "--team-size", help="Preferred agent count. 0 means auto."),
    output_dir: str = typer.Option("", "--output-dir", help="Optional output directory override."),
    language: str = typer.Option("", "--language", help="Language hint, e.g. zh-CN."),
    provider_json: str = typer.Option("", "--provider-json", help="Path to runtime provider JSON."),
    provider_type: str = typer.Option("openai_compatible", "--provider-type", help="openai_compatible | codex_cli"),
    provider_base_url: str = typer.Option("", "--provider-base-url", help="Provider base/completion URL."),
    provider_model: str = typer.Option("gpt-4.1", "--provider-model", help="Default model."),
    provider_key: str = typer.Option("", "--provider-key", help="Provider API key/token."),
    provider_timeout_s: int = typer.Option(0, "--provider-timeout-s", help="Provider timeout seconds. 0 means provider default."),
    strict_online: bool = typer.Option(True, "--strict-online/--allow-offline"),
    realtime_distill: bool = typer.Option(True, "--realtime-distill/--use-cache"),
    min_turns_per_member: int = typer.Option(0, "--min-turns-per-member", help="Minimum speaking turns per member. 0 means default."),
    turn_length: str = typer.Option("", "--turn-length", help="brief | standard | long | extended"),
    interaction_style: str = typer.Option("", "--interaction-style", help="Custom free-salon interaction style."),
    include_celebrities: str = typer.Option("", "--include-celebrities", help="Comma-separated names to include."),
    exclude_celebrities: str = typer.Option("", "--exclude-celebrities", help="Comma-separated names to exclude."),
    selection_mode: str = typer.Option("auto", "--selection-mode", help="auto | prefer | strict"),
) -> None:
    settings = Settings.from_env()
    if selection_mode not in {"auto", "prefer", "strict"}:
        raise typer.BadParameter("--selection-mode must be one of: auto, prefer, strict")
    if turn_length and turn_length not in {"brief", "standard", "long", "extended"}:
        raise typer.BadParameter("--turn-length must be one of: brief, standard, long, extended")
    runtime = _runtime_from_options(
        provider_json=provider_json,
        provider_type=provider_type,
        provider_base_url=provider_base_url,
        provider_model=provider_model,
        provider_key=provider_key,
        provider_timeout_s=provider_timeout_s,
        strict_online=strict_online,
        realtime_distill=realtime_distill,
        min_turns_per_member=min_turns_per_member,
        turn_length=turn_length,
        interaction_style=interaction_style,
    )
    root = Path(output_dir).resolve() if output_dir else settings.output_dir
    requested_size = team_size if team_size > 0 else None
    result = run_pipeline(
        query=query,
        requested_team_size=requested_size,
        settings=settings,
        output_root=root,
        language_hint=language or None,
        runtime=runtime,
        include_celebrities=[name.strip() for name in include_celebrities.split(",") if name.strip()],
        exclude_celebrities=[name.strip() for name in exclude_celebrities.split(",") if name.strip()],
        selection_mode=selection_mode,  # type: ignore[arg-type]
    )
    console.print(f"[bold green]Run completed:[/bold green] {result.run_dir}")
    console.print(f"[bold]Selected:[/bold] {', '.join(item.name for item in result.selection.selected)}")
    console.print(f"[bold]Report:[/bold] {Path(result.run_dir) / 'report.md'}")


@app.command("list-skills")
def list_skills(
    data_dir: str = typer.Option("", "--data-dir", help="Optional data root override."),
) -> None:
    settings = Settings.from_env()
    root = Path(data_dir).resolve() if data_dir else settings.data_dir
    skill_root = root / "celebrities" / "distilled_skills"
    table = Table(title="Cached Distilled Skills")
    table.add_column("Slug")
    table.add_column("Path")
    if not skill_root.exists():
        console.print(f"No skill cache found: {skill_root}")
        return
    for path in sorted(skill_root.iterdir()):
        if path.is_dir() and (path / "SKILL.md").exists():
            table.add_row(path.name, str(path / "SKILL.md"))
    console.print(table)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
