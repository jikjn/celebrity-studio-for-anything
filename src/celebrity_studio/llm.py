from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

from .config import Settings


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        ...

    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        ...


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
    raise LLMError("Model did not return valid JSON.")


@dataclass(slots=True)
class OpenAIChatClient:
    settings: Settings

    def __post_init__(self) -> None:
        if not self.settings.openai_api_key:
            raise LLMError("OPENAI_API_KEY is required for online mode.")
        try:
            from openai import OpenAI  # type: ignore
        except Exception as exc:  # pragma: no cover - import guard
            raise LLMError("openai package is not installed.") from exc
        self._client = OpenAI(
            api_key=self.settings.openai_api_key,
            base_url=self.settings.openai_base_url,
            timeout=self.settings.request_timeout_s,
        )

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        response = self._client.chat.completions.create(
            model=self.settings.model,
            temperature=self.settings.temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content or "{}"
        return _extract_json(content)

    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self.settings.model,
            temperature=self.settings.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""


def create_llm_client(settings: Settings) -> LLMClient | None:
    if settings.offline:
        return None
    if not settings.openai_api_key:
        return None
    try:
        return OpenAIChatClient(settings)
    except LLMError:
        return None

