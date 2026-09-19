"""The agent's only path to TigerGraph: the official tigergraph-mcp server over stdio.

The server is started with ``TG_ALLOWED_TOOLS`` so it exposes installed-query execution and vector
search only: no raw GSQL, no schema changes, no deletes. Writes happen solely through the installed
``write_case`` / ``add_case_event`` / ``delete_case`` queries. One session is held open for a whole
run (the MCP docs measure ~4x speed-up versus a session per call).
"""

import json
import logging
import os
import sys
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from redthread import config  # noqa: F401  (loads .env)

log = logging.getLogger(__name__)
ALLOWED_TOOLS = "run_installed_query,search_top_k_similarity,is_query_installed,get_graph_schema"
RUN_QUERY_TOOL = "tigergraph__run_installed_query"

# pyTigerGraph (inside the MCP server) warns on plain vertex params but handles them correctly.
logging.getLogger("pyTigerGraph").setLevel(logging.ERROR)


class GraphToolError(RuntimeError):
    pass


@dataclass
class CallRecord:
    query: str
    params: dict
    seconds: float


@dataclass
class McpGraph:
    """Async context manager holding one MCP session to the TigerGraph server."""

    calls: list[CallRecord] = field(default_factory=list)
    _stack: AsyncExitStack | None = None
    _session: ClientSession | None = None

    async def __aenter__(self) -> "McpGraph":
        exe = os.path.join(os.path.dirname(sys.executable), "tigergraph-mcp")
        env = {**os.environ, "TG_ALLOWED_TOOLS": ALLOWED_TOOLS}
        self._stack = AsyncExitStack()
        read, write = await self._stack.enter_async_context(
            stdio_client(StdioServerParameters(command=exe, args=[], env=env)))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        tools = {t.name for t in (await self._session.list_tools()).tools}
        if RUN_QUERY_TOOL not in tools or any("gsql" in t or "drop" in t or "delete" in t for t in tools):
            raise GraphToolError(f"unexpected MCP tool surface: {sorted(tools)}")
        log.info("MCP session open; tools: %s", sorted(tools))
        return self

    async def __aexit__(self, *exc) -> None:
        if self._stack:
            await self._stack.aclose()

    async def query(self, name: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Run an installed query through MCP and return its PRINT results."""
        params = params or {}
        start = time.time()
        result = await self._session.call_tool(RUN_QUERY_TOOL, {"query_name": name, "params": params})
        elapsed = time.time() - start
        self.calls.append(CallRecord(name, params, round(elapsed, 3)))
        text = "".join(getattr(c, "text", "") for c in result.content)
        payload = _parse(text)
        if getattr(result, "isError", False) or getattr(result, "is_error", False) or not payload.get("success"):
            raise GraphToolError(f"{name}({params}) failed: {text[:800]}")
        return payload["data"]["result"]


def _parse(text: str) -> dict:
    """The server wraps its JSON in a markdown code fence and may append notes after it; decode
    exactly one JSON object starting at the first brace."""
    start = text.find("{")
    try:
        payload, _ = json.JSONDecoder().raw_decode(text[start:])
        return payload
    except (json.JSONDecodeError, ValueError) as exc:
        raise GraphToolError(f"unparseable MCP response: {text[:500]}") from exc
