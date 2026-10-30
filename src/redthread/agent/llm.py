"""Gemini client with retries and per-case token accounting."""

import asyncio
import hashlib
import json
import logging
import os
import random

from google import genai
from google.genai import errors, types

from redthread import config, paths

log = logging.getLogger(__name__)
RETRYABLE = (429, 500, 502, 503, 504)
CALL_TIMEOUT_S = 240  # one model call; thinking=high can take a while, but never forever
# After this many timeouts in one call, the remaining attempts think less. Same model, same prompt and
# schema; only the reasoning budget shrinks. HHF-009's assessment timed out at "high" four times in a
# row on 29 Oct while every other case answered. The step-down is recorded (Llm.degraded) and shown in
# the case's events: a cheaper answer is acceptable, an undisclosed one is not.
STEP_DOWN_AFTER_TIMEOUTS = 2
STEP_DOWN_LEVEL = "low"
# Same inputs, same answer. Every model response is stored under a hash of everything that went into
# the call (model, system prompt, contents, tools, schema, temperature, thinking level). An identical
# call later reuses it, so an investigation run twice on an unchanged graph gives the same judgements
# and the same answer; any change in the evidence changes the hash and gets a fresh call. Two runs of
# one alert without this differed by 0.09 in probability (the same-case drill, 29 Oct). Each reuse is
# recorded in the case's events. REDTHREAD_LLM_REPLAY=off turns it off.
REPLAY_DIR = paths.ROOT / "runs" / "llm_replay"


class ModelError(RuntimeError):
    """The model could not be reached, timed out on every attempt, or refused the request."""


class Llm:
    def __init__(self) -> None:
        self.client = genai.Client()
        self.tokens = 0
        self.degraded: list[str] = []  # calls answered at a lower thinking level, for the audit trail
        self.reused: list[str] = []  # calls answered from an identical earlier call, for the audit trail
        self.replay = os.environ.get("REDTHREAD_LLM_REPLAY", "on") != "off"

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

        key = hashlib.sha256(json.dumps({
            "model": model or config.REASONING_MODEL, "system": system, "temperature": temperature,
            "thinking": config.THINKING_LEVEL, "schema": response_schema,
            "contents": [c.model_dump(mode="json", exclude_none=True) for c in contents],
            "tools": [t.model_dump(mode="json", exclude_none=True) for t in tools or []],
        }, sort_keys=True, default=str).encode()).hexdigest()
        stored = REPLAY_DIR / f"{key}.json"
        if getattr(self, "replay", False) and stored.exists():
            self.reused.append(key[:12])
            resp = types.GenerateContentResponse.model_validate_json(stored.read_text(encoding="utf-8"))
            # Counted at its recorded cost: the answer's token count is what its model calls consumed,
            # whether made now or answered from the store (each reuse is listed in the case's events).
            if resp.usage_metadata and resp.usage_metadata.total_token_count:
                self.tokens += resp.usage_metadata.total_token_count
            return resp

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
                elif getattr(self, "replay", False):  # a stepped-down answer is never stored as the answer
                    REPLAY_DIR.mkdir(parents=True, exist_ok=True)
                    stored.write_text(resp.model_dump_json(exclude_none=True), encoding="utf-8")
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
