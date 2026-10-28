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


class ModelError(RuntimeError):
    """The model could not be reached, timed out on every attempt, or refused the request."""


class Llm:
    def __init__(self) -> None:
        self.client = genai.Client()
        self.tokens = 0

    async def generate(self, contents: list[types.Content], *, system: str, model: str | None = None,
                       tools: list[types.Tool] | None = None, response_schema: dict | None = None,
                       temperature: float = 0.2, attempts: int = 4) -> types.GenerateContentResponse:
        thinking = types.ThinkingConfig(thinking_level=config.THINKING_LEVEL) if config.THINKING_LEVEL else None
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            thinking_config=thinking,
            tools=tools,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True) if tools else None,
            response_mime_type="application/json" if response_schema else None,
            response_json_schema=response_schema,
        )
        for attempt in range(1, attempts + 1):
            try:
                resp = await asyncio.wait_for(self.client.aio.models.generate_content(
                    model=model or config.REASONING_MODEL, contents=contents, config=cfg), CALL_TIMEOUT_S)
                if resp.usage_metadata and resp.usage_metadata.total_token_count:
                    self.tokens += resp.usage_metadata.total_token_count
                return resp
            except TimeoutError:
                why = f"no response within {CALL_TIMEOUT_S}s"
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
