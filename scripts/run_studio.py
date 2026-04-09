from __future__ import annotations

import argparse

from celebrity_studio.config import Settings
from celebrity_studio.models import ProviderConfig, RuntimeConfig
from celebrity_studio.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Celebrity Studio pipeline.")
    parser.add_argument("--query", "-q", required=True, help="Scenario query.")
    parser.add_argument("--team-size", type=int, default=0, help="Preferred team size.")
    parser.add_argument("--offline", action="store_true", help="Force offline mode.")
    parser.add_argument("--language", default="", help="Language hint.")
    parser.add_argument("--provider-type", default="openai_compatible")
    parser.add_argument("--provider-base-url", default="")
    parser.add_argument("--provider-model", default="gpt-4.1")
    parser.add_argument("--provider-key", default="")
    parser.add_argument("--provider-timeout-s", type=int, default=0)
    parser.add_argument("--include-celebrities", default="", help="Comma-separated names to include.")
    parser.add_argument("--exclude-celebrities", default="", help="Comma-separated names to exclude.")
    parser.add_argument("--selection-mode", default="auto", help="auto | prefer | strict")
    args = parser.parse_args()

    settings = Settings.from_env()
    if args.offline:
        settings.offline = True
    runtime = RuntimeConfig(strict_online=not args.offline, realtime_distill=not args.offline)
    use_provider = bool(args.provider_key) or args.provider_type == "codex_cli"
    if use_provider:
        timeout_s = args.provider_timeout_s if args.provider_timeout_s > 0 else (300 if args.provider_type == "codex_cli" else 120)
        runtime.providers = [
            ProviderConfig(
                provider_id="default",
                provider_type=args.provider_type,
                model=args.provider_model,
                api_key=args.provider_key,
                base_url=args.provider_base_url,
                timeout_s=timeout_s,
            )
        ]
        runtime.default_provider_id = "default"
        runtime.leader_provider_id = "default"
    if args.selection_mode not in {"auto", "prefer", "strict"}:
        raise ValueError("--selection-mode must be one of: auto, prefer, strict")
    result = run_pipeline(
        query=args.query,
        requested_team_size=args.team_size if args.team_size > 0 else None,
        settings=settings,
        language_hint=args.language or None,
        runtime=runtime,
        include_celebrities=[name.strip() for name in args.include_celebrities.split(",") if name.strip()],
        exclude_celebrities=[name.strip() for name in args.exclude_celebrities.split(",") if name.strip()],
        selection_mode=args.selection_mode,
    )
    print(result.run_dir)


if __name__ == "__main__":
    main()
