from __future__ import annotations

from pathlib import Path
from typing import Any
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Settings
from .models import ProviderConfig, RuntimeConfig
from .pipeline import run_pipeline
from .utils import read_json


class RunRequest(BaseModel):
    query: str
    team_size: int | None = None
    language_hint: str | None = None
    include_celebrities: list[str] = Field(default_factory=list)
    exclude_celebrities: list[str] = Field(default_factory=list)
    selection_mode: Literal["auto", "prefer", "strict"] = "auto"
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)


class RunSummary(BaseModel):
    scenario_id: str
    run_dir: str
    selected: list[str]
    challenge_edges: list[dict[str, Any]]
    report_markdown: str
    result: dict[str, Any]


def create_app() -> FastAPI:
    settings = Settings.from_env()
    app = FastAPI(title="MindForge Studio API", version="0.3.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    web_root = settings.workspace_root / "web"
    if web_root.exists():
        app.mount("/static", StaticFiles(directory=str(web_root), html=False), name="static")

    @app.get("/")
    def index() -> FileResponse:
        index_path = web_root / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="Frontend not found.")
        return FileResponse(str(index_path))

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/studio/run", response_model=RunSummary)
    def run_studio(payload: RunRequest) -> RunSummary:
        try:
            result = run_pipeline(
                query=payload.query,
                requested_team_size=payload.team_size,
                settings=settings,
                language_hint=payload.language_hint,
                runtime=payload.runtime,
                include_celebrities=payload.include_celebrities,
                exclude_celebrities=payload.exclude_celebrities,
                selection_mode=payload.selection_mode,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return RunSummary(
            scenario_id=result.scenario.scenario_id,
            run_dir=result.run_dir,
            selected=[item.name for item in result.selection.selected],
            challenge_edges=[edge.model_dump() for edge in result.debate.challenge_edges],
            report_markdown=result.report_markdown,
            result=result.model_dump(),
        )

    @app.get("/api/studio/runs/{scenario_id}")
    def load_run(scenario_id: str) -> dict[str, Any]:
        run_path = settings.output_dir / scenario_id / "result.json"
        if not run_path.exists():
            raise HTTPException(status_code=404, detail="Run not found.")
        return read_json(run_path)

    @app.get("/api/provider/model-catalog")
    def model_catalog() -> dict[str, Any]:
        return {
            "provider_types": [
                {"id": "openai_compatible", "display_name": "OpenAI-Compatible", "requires_api_key": True},
                {"id": "codex_cli", "display_name": "Codex CLI", "requires_api_key": False},
            ],
            "model_input": {
                "mode": "freeform",
                "description": "Use any model id your endpoint/account supports.",
                "placeholder": "gpt-5.3-codex / gpt-4.1 / any-supported-model",
            },
            "runtime_payload_fields": {
                "providers[].api_key": "User-provided key/token for that provider.",
                "providers[].model": "Freeform model ID.",
                "discussion.min_turns_per_member": "Minimum speaking turns per member (default: 5).",
                "discussion.turn_length": "Turn length style: brief | standard | long | extended.",
                "discussion.interaction_style": "Free-form interaction style instruction from user.",
            },
        }

    @app.get("/api/provider/preset/codex-cli")
    def codex_preset() -> dict[str, Any]:
        return {
            "providers": [
                ProviderConfig(
                    provider_id="codex-local",
                    provider_type="codex_cli",
                    model="gpt-5.3-codex",
                    api_key="",
                    base_url="",
                    temperature=0.0,
                    timeout_s=300,
                    extra_headers={"codex_reasoning_effort": "medium"},
                ).model_dump()
            ],
            "default_provider_id": "codex-local",
            "leader_provider_id": "codex-local",
            "assignment_strategy": "round_robin",
            "realtime_distill": False,
            "strict_online": True,
            "discussion": {
                "mode": "free_salon",
                "min_turns_per_member": 5,
                "turn_length": "long",
                "interaction_style": "像同桌沙龙一样自由交流，允许质疑、支持、反驳、补充，不走模板话术，优先真实观点碰撞。",
            },
        }

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("celebrity_studio.api_server:app", host="0.0.0.0", port=8787, reload=False)
