import json
import time
import logging
from typing import Any

from openai import AsyncOpenAI, APITimeoutError, APIError, RateLimitError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import settings

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)


class AgentError(Exception):
    """Raised when an agent fails after all retries -- callers must handle this, never assume success."""


class BaseAgent:
    """
    Common wrapper for a single-purpose security agent backed by the OpenAI API.

    Design choices that matter for a defense product:
    - Every agent has ONE narrow job (triage / enrich / correlate / recommend) rather than one
      do-everything agent -- narrow scope = easier to audit, easier to evaluate, easier to constrain.
    - Output is forced into structured JSON (json_object mode) -- free text is not acceptable when
      downstream code and analysts need to parse a verdict programmatically.
    - The agent NEVER executes actions itself. It only returns a recommendation. Execution is a
      separate, explicitly-gated step (see orchestrator.py / response_agent.py).
    """

    name: str = "base_agent"
    system_prompt: str = "You are a helpful assistant."

    def __init__(self, model: str | None = None):
        self.model = model or settings.openai_model

    @retry(
        stop=stop_after_attempt(settings.openai_max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((APITimeoutError, RateLimitError)),
        reraise=True,
    )
    async def _call_model(self, user_content: str) -> dict[str, Any]:
        start = time.monotonic()
        try:
            response = await _client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                temperature=0,  # deterministic-as-possible for a defense/audit context
            )
        except (APITimeoutError, RateLimitError):
            raise
        except APIError as e:
            logger.error(f"[{self.name}] OpenAI API error: {e}")
            raise AgentError(f"{self.name} failed: {e}") from e

        latency_ms = int((time.monotonic() - start) * 1000)
        raw = response.choices[0].message.content

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise AgentError(f"{self.name} returned non-JSON output: {raw[:200]}") from e

        return {"output": parsed, "latency_ms": latency_ms, "model": self.model}

    async def run(self, payload: dict) -> dict:
        """Override in subclasses to shape the prompt; this base impl just stringifies payload."""
        user_content = self.build_prompt(payload)
        try:
            return await self._call_model(user_content)
        except Exception as e:
            raise AgentError(f"{self.name} failed after retries: {e}") from e

    def build_prompt(self, payload: dict) -> str:
        raise NotImplementedError
