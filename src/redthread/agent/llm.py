"""Gemini client with retries and per-case token accounting."""

import asyncio
import logging
import random

from google import genai
from google.genai import errors, types

from redthread import config

log = logging.getLogger(__name__)
RETRYABLE = (429, 500, 502, 503, 504)


class Llm:
    def __init__(self) -> None:
        self.client = genai.Client()
        self.tokens = 0

    async def generate(self, contents: list[types.Content], *, system: str, model: str | None = None,
                       tools: list[types.Tool] | None = None, response_schema: dict | None = None,
                       temperature: float = 0.2, attempts: int = 6) -> types.GenerateContentResponse:
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            tools=tools,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True) if tools else None,
            response_mime_type="application/json" if response_schema else None,
            response_json_schema=response_schema,
        )
        for attempt in range(1, attempts + 1):
            try:
                resp = await self.client.aio.models.generate_content(
                    model=model or config.REASONING_MODEL, contents=contents, config=cfg)
                if resp.usage_metadata and resp.usage_metadata.total_token_count:
                    self.tokens += resp.usage_metadata.total_token_count
                return resp
            except errors.APIError as exc:
                if exc.code not in RETRYABLE or attempt == attempts:
                    raise
                delay = min(60, 2 ** attempt) + random.random()
                log.warning("Gemini %s (attempt %d); retrying in %.0fs", exc.code, attempt, delay)
                await asyncio.sleep(delay)
        raise RuntimeError("unreachable")
