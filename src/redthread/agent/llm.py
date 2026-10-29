"""Gemini client with retries and per-case token accounting."""

import asyncio
import logging
import random

from google import genai
from google.genai import errors, types

from redthread import config

log = logging.getLogger(__name__)
RETRYABLE = (429, 500, 502, 503, 504)
CALL_TIMEOUT_S = 240  # one model call; thinking=high can take a while, but never forever
# After this many timeouts in one call, the remaining attempts think less. Same model, same prompt and
# schema; only the reasoning budget shrinks. HHF-009's assessment timed out at "high" four times in a
# row on 29 Oct while every other case answered. The step-down is recorded (Llm.degraded) and shown in
# the case's events: a cheaper answer is acceptable, an undisclosed one is not.
STEP_DOWN_AFTER_TIMEOUTS = 2
STEP_DOWN_LEVEL = "low"


class ModelError(RuntimeError):
    """The model could not be reached, timed out on every attempt, or refused the request."""


class Llm:
    def __init__(self) -> None:
        self.client = genai.Client()
        self.tokens = 0
        self.degraded: list[str] = []  # calls answered at a lower thinking level, for the audit trail

    async def generate(self, contents: list[types.Content], *, system: str, model: str | None = None,
                       tools: list[types.Tool] | None = None, response_schema: dict | None = None,
                       temperature: float = 0.2, attempts: int = 4) -> types.GenerateContentResponse:
        def config_for(level: str | None) -> types.GenerateContentConfig:
            return types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
                thinking_config=types.ThinkingConfig(thinking_level=level) if level else None,
                tools=tools,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True) if tools else None,
                response_mime_type="application/json" if response_schema else None,
                response_json_schema=response_schema,
            )

        level, timeouts = config.THINKING_LEVEL, 0
        for attempt in range(1, attempts + 1):
            try:
                resp = await asyncio.wait_for(self.client.aio.models.generate_content(
                    model=model or config.REASONING_MODEL, contents=contents, config=config_for(level)),
                    CALL_TIMEOUT_S)
                if resp.usage_metadata and resp.usage_metadata.total_token_count:
                    self.tokens += resp.usage_metadata.total_token_count
                if level != config.THINKING_LEVEL:
                    self.degraded.append(f"answered at thinking level {level!r} after {timeouts} timeout(s) at "
                                         f"{config.THINKING_LEVEL!r}")
                return resp
            except TimeoutError:
                why = f"no response within {CALL_TIMEOUT_S}s"
                timeouts += 1
                if timeouts >= STEP_DOWN_AFTER_TIMEOUTS and config.THINKING_LEVEL:
                    level = STEP_DOWN_LEVEL
            except errors.APIError as exc:
                if exc.code not in RETRYABLE:
                    raise ModelError(f"model refused the request: {exc.code} {exc.message}") from exc
                why = f"error {exc.code}"
            except Exception as exc:  # transport failures: the model is unreachable
                why = f"{type(exc).__name__}: {exc}"
            if attempt == attempts:
                raise ModelError(f"model unavailable after {attempts} attempts ({why})")
            delay = min(30, 2 ** attempt) + random.random()
            log.warning("model call failed (%s, attempt %d); retrying in %.0fs", why, attempt, delay)
            await asyncio.sleep(delay)
        raise RuntimeError("unreachable")
