from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "y", "on"}


@dataclass(slots=True)
class Settings:
    model: str
    openai_api_key: str | None
    openai_base_url: str | None
    temperature: float
    request_timeout_s: int
    offline: bool
    min_agents: int
    max_agents: int
    workspace_root: Path
    data_dir: Path
    output_dir: Path

    @staticmethod
    def from_env(workspace_root: Path | None = None) -> "Settings":
        root = workspace_root or Path(__file__).resolve().parents[2]
        data_dir = root / "data"
        output_dir = root / "outputs"
        return Settings(
            model=os.getenv("CELEBRITY_STUDIO_MODEL", "gpt-4.1"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_base_url=os.getenv("OPENAI_BASE_URL"),
            temperature=float(os.getenv("CELEBRITY_STUDIO_TEMPERATURE", "0.25")),
            request_timeout_s=int(os.getenv("CELEBRITY_STUDIO_TIMEOUT", "90")),
            offline=_to_bool(os.getenv("CELEBRITY_STUDIO_OFFLINE"), False),
            min_agents=max(2, int(os.getenv("CELEBRITY_STUDIO_MIN_AGENTS", "4"))),
            max_agents=max(4, int(os.getenv("CELEBRITY_STUDIO_MAX_AGENTS", "8"))),
            workspace_root=root,
            data_dir=data_dir,
            output_dir=output_dir,
        )

