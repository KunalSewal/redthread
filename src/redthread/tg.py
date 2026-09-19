"""TigerGraph connection for scripts and the backend (the agent itself goes through MCP)."""

import os
from functools import cache

from pyTigerGraph import TigerGraphConnection

from redthread import config  # noqa: F401  (loads .env)

GRAPH = os.getenv("TG_GRAPHNAME", "RedThread")


@cache
def connection(graph: str | None = GRAPH) -> TigerGraphConnection:
    return TigerGraphConnection(
        host=os.environ["TG_HOST"],
        graphname=graph or "",
        username=os.environ["TG_USERNAME"],
        password=os.environ["TG_PASSWORD"],
        restppPort=os.getenv("TG_RESTPP_PORT", "443"),
        gsPort=os.getenv("TG_GS_PORT", "443"),
        tgCloud=os.getenv("TG_TGCLOUD", "true").lower() == "true",
    )
