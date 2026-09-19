"""Create the schema, loading jobs and data in TigerGraph. Every step is safe to rerun.

    python scripts/setup_graph.py all        # schema -> vectors -> jobs -> load
    python scripts/setup_graph.py status     # vertex/edge counts
    python scripts/setup_graph.py load       # (re)load data; skips files already loaded
    python scripts/setup_graph.py load --force

Loaded files are recorded in data/processed/.load_state.json so a run interrupted by Savanna's
auto-suspend resumes where it stopped. Upserts are idempotent, so reloading a file is harmless.
"""

import argparse
import json
import logging
import re
import sys
import time

from redthread import paths
from redthread.tg import GRAPH, connection

log = logging.getLogger("setup_graph")
STATE = paths.PROCESSED / ".load_state.json"

# (loading job, file glob) in dependency-free order; edges auto-create missing endpoint vertices.
LOADS = [
    ("load_patterns", "patterns.csv"),
    ("load_customers", "customers.csv"),
    ("load_cards", "cards.csv"),
    ("load_holders", "holders.csv"),
    ("load_devices", "devices.csv"),
    ("load_transactions", "transactions_*.csv"),
    ("load_card_device", "card_device.csv"),
    ("load_next", "next_edges.csv"),
    ("load_closed_cases", "closed_cases.csv"),
    ("load_closed_case_involves", "closed_case_involves.csv"),
    ("load_closed_case_connected", "closed_case_connected.csv"),
]


ERROR_MARKERS = ("semantic check fails", "syntax error", "failed", "error:", "encountered \"",
                 "was expecting", "does not have the permission")
ALREADY_EXISTS = ("already exist", "is used by another object", "conflicts with")


class GsqlError(RuntimeError):
    pass


def gsql(text: str, graph: str | None = GRAPH) -> str:
    out = connection(None).gsql(text if graph is None else f"USE GRAPH {graph}\n{text}")
    if any(s in out.lower() for s in ERROR_MARKERS):
        raise GsqlError(out)
    return out


def statements(path) -> list[str]:
    """Split a GSQL file into top-level statements (each starts with CREATE/RUN), comments dropped."""
    lines = [ln for ln in path.read_text().splitlines() if not ln.strip().startswith("//")]
    return [s.strip() for s in re.split(r"\n(?=CREATE |RUN )", "\n".join(lines)) if s.strip()]


def run_idempotent(stmts: list[str], graph: str | None) -> None:
    for stmt in stmts:
        head = stmt.splitlines()[0][:80]
        try:
            gsql(stmt, graph=graph)
            log.info("ok      %s", head)
        except GsqlError as exc:
            if any(s in str(exc).lower() for s in ALREADY_EXISTS):
                log.info("exists  %s", head)
            else:
                raise GsqlError(f"{head}\n{exc}") from None


def graph_exists() -> bool:
    return GRAPH in gsql("SHOW GRAPH *", graph=None)


def step_schema() -> None:
    if graph_exists():
        log.info("graph %s exists; skipping schema", GRAPH)
        return
    run_idempotent(statements(paths.GSQL / "01_schema.gsql"), graph=None)


def step_vectors() -> None:
    if "emb(" in gsql("LS"):  # vector attributes appear in the vertex listing
        log.info("vector attributes exist; skipping")
        return
    log.info("%s", gsql((paths.GSQL / "01b_vectors.gsql").read_text(), graph=None)[-400:])


def step_jobs() -> None:
    jobs = [s for s in statements(paths.GSQL / "02_loading.gsql") if s.startswith("CREATE LOADING JOB")]
    run_idempotent(jobs, graph=GRAPH)


def _state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def step_load(force: bool = False) -> None:
    conn = connection()
    state = {} if force else _state()
    for job, pattern in LOADS:
        for path in sorted(paths.PROCESSED.glob(pattern)):
            key = f"{job}:{path.name}"
            if key in state:
                log.info("skip %-40s (loaded %s)", key, state[key]["at"])
                continue
            start = time.time()
            result = conn.runLoadingJobWithFile(str(path), "f", job, sep=",", eol="\n", timeout=0)
            stats = _summarize(result)
            state[key] = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "secs": round(time.time() - start, 1), **stats}
            STATE.write_text(json.dumps(state, indent=2))
            log.info("loaded %-40s %s in %.0fs", key, stats, time.time() - start)
            if stats.get("rejected"):
                log.warning("rejected lines in %s: %s", path.name, json.dumps(result)[:600])


def _summarize(result) -> dict:
    """Pull valid/rejected line counts out of the loading-job response."""
    try:
        stats = result[0]["statistics"]
        return {"valid": stats.get("validLine", 0), "rejected": stats.get("rejectLine", 0)
                + stats.get("invalidJson", 0) + stats.get("notEnoughToken", 0)}
    except (KeyError, IndexError, TypeError):
        return {"raw": str(result)[:300]}


def step_status() -> None:
    conn = connection()
    for vtype, count in sorted(conn.getVertexCount("*").items()):
        print(f"vertex {vtype:16} {count:>10,}")
    for etype, count in sorted(conn.getEdgeCount("*").items()):
        if count:
            print(f"edge   {etype:22} {count:>10,}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["all", "schema", "vectors", "jobs", "load", "status"])
    parser.add_argument("--force", action="store_true", help="reload files already marked loaded")
    args = parser.parse_args()
    steps = {
        "schema": [step_schema], "vectors": [step_vectors], "jobs": [step_jobs],
        "load": [lambda: step_load(args.force)], "status": [step_status],
        "all": [step_schema, step_vectors, step_jobs, lambda: step_load(args.force), step_status],
    }
    for fn in steps[args.step]:
        fn()


if __name__ == "__main__":
    sys.exit(main())
