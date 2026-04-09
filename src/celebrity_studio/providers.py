from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .config import Settings
from .models import ProviderConfig, RuntimeConfig


class ProviderError(RuntimeError):
    pass


def _extract_json(payload: str) -> dict:
    content = payload.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))

    brace = re.search(r"\{.*\}", content, re.DOTALL)
    if brace:
        return json.loads(brace.group(0))

    raise ProviderError("Model response does not contain valid JSON.")


def _message_content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    chunks.append(text)
                else:
                    chunks.append(json.dumps(item, ensure_ascii=False))
            else:
                chunks.append(str(item))
        return "\n".join(chunks)
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text
        return json.dumps(content, ensure_ascii=False)
    return str(content)


class ChatProvider(Protocol):
    provider_id: str
    model: str

    def chat(self, messages: list[dict], model: str | None = None, temperature: float | None = None, json_mode: bool = False) -> str:
        ...

    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        ...

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        ...


@dataclass(slots=True)
class OpenAICompatibleProvider:
    provider_id: str
    model: str
    api_key: str
    base_url: str
    temperature: float
    timeout_s: int
    _client: object = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ProviderError(f"Provider {self.provider_id}: missing api_key.")
        try:
            from openai import OpenAI  # type: ignore
        except Exception as exc:
            raise ProviderError("openai package is required for OpenAI-compatible providers.") from exc
        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url or None, timeout=self.timeout_s)

    def chat(self, messages: list[dict], model: str | None = None, temperature: float | None = None, json_mode: bool = False) -> str:
        kwargs = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = self._client.chat.completions.create(
            model=model or self.model,
            temperature=self.temperature if temperature is None else temperature,
            messages=messages,
            **kwargs,
        )
        return response.choices[0].message.content or ""

    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        return self.chat(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            json_mode=False,
        )

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        content = self.chat(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            json_mode=True,
        )
        return _extract_json(content)


@dataclass(slots=True)
class CodexCliProvider:
    provider_id: str
    model: str
    api_key: str
    base_url: str
    temperature: float
    timeout_s: int
    extra_headers: dict[str, str]
    _codex_cmd: str = field(init=False, repr=False)
    _cwd: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        cmd_hint = self.base_url.strip()
        self._codex_cmd = self._resolve_codex_command(cmd_hint)
        self._cwd = self._resolve_cwd()

    @staticmethod
    def _resolve_codex_command(cmd_hint: str) -> str:
        candidates: list[str] = []

        if cmd_hint:
            candidates.append(cmd_hint)

        env_hint = os.getenv("CODEX_CLI_PATH", "").strip()
        if env_hint:
            candidates.append(env_hint)

        appdata = os.getenv("APPDATA", "").strip()
        if appdata:
            candidates.append(str(Path(appdata) / "npm" / "codex.cmd"))

        candidates.extend(["codex.cmd", "codex"])

        for candidate in candidates:
            cleaned = candidate.strip().strip('"')
            if not cleaned:
                continue
            path = Path(cleaned)
            if path.is_file():
                return str(path)
            resolved = shutil.which(cleaned)
            if resolved:
                return resolved

        raise ProviderError(
            "Codex CLI executable not found. Set Provider.base_url or CODEX_CLI_PATH to codex.cmd path."
        )

    def _resolve_cwd(self) -> str:
        raw = str(self.extra_headers.get("codex_cwd", "")).strip()
        if raw:
            path = Path(raw)
            if path.exists() and path.is_dir():
                return str(path)
            raise ProviderError(f"codex_cwd does not exist or is not a directory: {raw}")
        return str(Path.cwd())

    def _compose_prompt(self, messages: list[dict], json_mode: bool) -> str:
        if not messages:
            return "{}" if json_mode else ""

        last_user_text = ""
        for msg in reversed(messages):
            if str(msg.get("role", "")).lower() == "user":
                last_user_text = _message_content_text(msg.get("content", ""))
                break
        if not last_user_text:
            last_user_text = _message_content_text(messages[-1].get("content", ""))

        context_items: list[str] = []
        for msg in messages[:-1]:
            role = str(msg.get("role", "user")).upper()
            content_text = _message_content_text(msg.get("content", "")).strip()
            if not content_text:
                continue
            context_items.append(f"[{role}] {content_text}")

        lines: list[str] = [
            "Respond to the request below immediately.",
            "Do not ask clarifying questions.",
        ]
        if json_mode:
            lines.append("Return exactly one JSON object and no extra text.")
        else:
            lines.append("Return only the final answer text.")

        if context_items:
            lines.append("")
            lines.append("Context:")
            lines.extend(context_items[-12:])

        lines.append("")
        lines.append("Request:")
        lines.append(last_user_text)
        return "\n".join(lines).strip()

    def _resolved_model(self, requested_model: str | None) -> str | None:
        candidate = (requested_model or self.model or "").strip()
        if not candidate:
            return None
        # gpt-4.1 is the global project default but often unsupported in Codex CLI account mode.
        if candidate in {"auto", "default", "gpt-4.1"}:
            return None
        return candidate

    def chat(self, messages: list[dict], model: str | None = None, temperature: float | None = None, json_mode: bool = False) -> str:
        prompt = self._compose_prompt(messages, json_mode=json_mode)
        selected_model = self._resolved_model(model)
        effort = str(self.extra_headers.get("codex_reasoning_effort", "medium")).strip().lower()
        if effort not in {"low", "medium", "high", "xhigh"}:
            effort = "medium"

        fd, tmp_path = tempfile.mkstemp(prefix="codex-provider-", suffix=".txt")
        os.close(fd)
        try:
            cmd = [
                self._codex_cmd,
                "exec",
                "--skip-git-repo-check",
                "--cd",
                self._cwd,
                "--sandbox",
                "read-only",
                "--color",
                "never",
                "--output-last-message",
                tmp_path,
                "-c",
                f'model_reasoning_effort="{effort}"',
                "-c",
                "mcp_servers.linear.enabled=false",
                "-c",
                "mcp_servers.playwright.enabled=false",
            ]
            if selected_model:
                cmd.extend(["--model", selected_model])

            # Use stdin mode ("-") to preserve multiline prompts reliably.
            cmd.append("-")

            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    input=prompt,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=max(20, self.timeout_s),
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise ProviderError(f"Codex CLI timed out after {max(20, self.timeout_s)}s") from exc

            content = Path(tmp_path).read_text(encoding="utf-8", errors="replace").strip()
            if proc.returncode != 0:
                stderr_text = proc.stderr or ""
                stdout_text = proc.stdout or ""
                merged = "\n".join(part for part in [stderr_text, stdout_text] if part).strip()
                detail = merged
                error_lines = [line.strip() for line in merged.splitlines() if line.strip().startswith("ERROR:")]
                if error_lines:
                    detail = error_lines[-1]
                elif "usage limit" in merged.lower():
                    detail = "Codex CLI usage limit reached."
                elif len(detail) > 500:
                    detail = detail[-500:]
                raise ProviderError(f"Codex CLI provider error (exit={proc.returncode}): {detail}")

            if not content:
                raise ProviderError("Codex CLI returned empty content.")

            return content
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass

    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        return self.chat(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            json_mode=False,
        )

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        content = self.chat(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            json_mode=True,
        )
        return _extract_json(content)


@dataclass(slots=True)
class ProviderRegistry:
    providers: dict[str, ChatProvider]
    default_provider_id: str
    leader_provider_id: str | None = None
    assignment_strategy: str = "round_robin"

    def get(self, provider_id: str | None = None) -> ChatProvider:
        pid = provider_id or self.default_provider_id
        provider = self.providers.get(pid)
        if provider is None:
            raise ProviderError(f"Provider '{pid}' is not configured.")
        return provider

    def default(self) -> ChatProvider:
        return self.get(self.default_provider_id)

    def leader(self) -> ChatProvider:
        if self.leader_provider_id:
            return self.get(self.leader_provider_id)
        return self.default()


@dataclass(slots=True)
class LLMClientAdapter:
    provider: ChatProvider

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        return self.provider.complete_json(system_prompt, user_prompt)

    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        return self.provider.complete_text(system_prompt, user_prompt)


def _provider_from_config(config: ProviderConfig) -> ChatProvider:
    if config.provider_type == "openai_compatible":
        return OpenAICompatibleProvider(
            provider_id=config.provider_id,
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
            temperature=config.temperature,
            timeout_s=config.timeout_s,
        )

    if config.provider_type == "codex_cli":
        return CodexCliProvider(
            provider_id=config.provider_id,
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
            temperature=config.temperature,
            timeout_s=config.timeout_s,
            extra_headers=config.extra_headers,
        )

    raise ProviderError(f"Unsupported provider type: {config.provider_type}")


def build_registry(runtime: RuntimeConfig | None, settings: Settings) -> ProviderRegistry | None:
    if runtime and runtime.providers:
        providers: dict[str, ChatProvider] = {}
        for cfg in runtime.providers:
            providers[cfg.provider_id] = _provider_from_config(cfg)
        default_provider_id = runtime.default_provider_id or runtime.providers[0].provider_id
        return ProviderRegistry(
            providers=providers,
            default_provider_id=default_provider_id,
            leader_provider_id=runtime.leader_provider_id,
            assignment_strategy=runtime.assignment_strategy,
        )

    if settings.offline:
        return None
    if not settings.openai_api_key:
        return None

    default_cfg = ProviderConfig(
        provider_id="default",
        provider_type="openai_compatible",
        model=settings.model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or "",
        temperature=settings.temperature,
        timeout_s=settings.request_timeout_s,
    )
    provider = _provider_from_config(default_cfg)
    return ProviderRegistry(providers={"default": provider}, default_provider_id="default")


def registry_to_llm_adapter(registry: ProviderRegistry | None) -> LLMClientAdapter | None:
    if registry is None:
        return None
    return LLMClientAdapter(provider=registry.default())
