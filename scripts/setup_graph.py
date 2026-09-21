"""Create the schema, loading jobs and data in TigerGraph. Every step is safe to rerun.

    python scripts/setup_graph.py all        # schema -> schema_changes -> jobs -> load -> queries
    python scripts/setup_graph.py status     # vertex/edge counts
    python scripts/setup_graph.py load       # (re)load data; skips files already loaded
    python scripts/setup_graph.py load --force

Loaded files are recorded in data/processed/.load_state.json so a run interrupted by Savanna's
auto-suspend resumes where it stopped. Upserts are idempotent, so reloading a file is harmless.
"""

import argparse
import csv
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
# Jobs whose files are produced later (GraphRAG ingestion) declare their columns here.
FIXED_HEADERS = {"load_doc_chunks": ["chunk_id", "source", "section", "content"]}


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
    try:
        return GRAPH in gsql("SHOW GRAPH *", graph=None)
    except GsqlError as exc:
        if "no graph available" in str(exc).lower():
            return False
        raise


def step_schema() -> None:
    if graph_exists():
        log.info("graph %s exists; skipping schema", GRAPH)
        return
    run_idempotent(statements(paths.GSQL / "01_schema.gsql"), graph=None)


def _has_attribute(vertex: str, attribute: str) -> bool:
    return any(a["AttributeName"] == attribute for a in connection().getVertexType(vertex)["Attributes"])


# (file, check that returns True once applied). Global schema changes run once each.
SCHEMA_CHANGES = [
    ("01b_vectors.gsql", lambda: "emb(" in gsql("LS")),
    ("01c_rings.gsql", lambda: _has_attribute("Card", "ring_id")),
    ("01d_device_rings.gsql", lambda: _has_attribute("DeviceProfile", "ring_id")),
    ("01e_gds_attrs.gsql", lambda: _has_attribute("Card", "community_id")),
]


def step_schema_changes() -> None:
    for name, applied in SCHEMA_CHANGES:
        if applied():
            log.info("schema change %s already applied", name)
            continue
        log.info("%s", gsql((paths.GSQL / name).read_text(), graph=None)[-300:])


def step_queries(names: list[str] | None = None) -> None:
    """Create (or replace) every query in 03_queries.gsql, then install them in one compile."""
    stmts = [s for s in statements(paths.GSQL / "03_queries.gsql") if s.startswith("CREATE OR REPLACE QUERY")]
    created = []
    for stmt in stmts:
        name = re.match(r"CREATE OR REPLACE QUERY (\w+)", stmt).group(1)
        if names and name not in names:
            continue
        gsql(stmt)
        created.append(name)
        log.info("created query %s", name)
    start = time.time()
    out = gsql(f"INSTALL QUERY {', '.join(created)}")
    log.info("installed %d queries in %.0fs: %s", len(created), time.time() - start, out[-300:])


def header_for(job: str) -> list[str] | None:
    """Column names of the file a job loads, read from the CSV itself."""
    if job in FIXED_HEADERS:
        return FIXED_HEADERS[job]
    pattern = dict(LOADS).get(job)
    files = sorted(paths.PROCESSED.glob(pattern)) if pattern else []
    if not files:
        return None
    with files[0].open(encoding="utf-8") as fh:
        return next(csv.reader(fh))


def positional(stmt: str) -> str:
    """Rewrite $"column" to $N. TigerGraph only resolves header names when the job's file path is
    fixed at creation time; ours are posted at run time, so positions come from the CSV headers."""
    job = re.match(r"CREATE LOADING JOB (\w+)", stmt).group(1)
    names = re.findall(r'\$"(\w+)"', stmt)
    if not names:
        return stmt
    header = header_for(job)
    if header is None:
        raise GsqlError(f"no header known for {job}")
    missing = sorted(set(names) - set(header))
    if missing:
        raise GsqlError(f"{job}: columns {missing} not in file header {header}")
    return re.sub(r'\$"(\w+)"', lambda m: f"${header.index(m.group(1))}", stmt)


def step_jobs() -> None:
    """(Re)create every loading job. Jobs hold no data, so dropping and recreating is cheap and keeps
    them in sync with 02_loading.gsql."""
    jobs = [positional(s) for s in statements(paths.GSQL / "02_loading.gsql") if s.startswith("CREATE LOADING JOB")]
    for job in jobs:
        name = re.match(r"CREATE LOADING JOB (\w+)", job).group(1)
        try:
            gsql(f"DROP JOB {name}")
        except GsqlError:
            pass  # did not exist
    run_idempotent(jobs, graph=GRAPH)


def _state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def load_file(job: str, path, sep: str = ",", has_header: bool = True) -> dict:
    """Post one file to a loading job (header stripped) and check every data line was accepted."""
    text = path.read_text(encoding="utf-8")
    body = text.partition("\n")[2] if has_header else text
    expected = body.count("\n") + (0 if body.endswith("\n") or not body else 1)
    result = connection().runLoadingJobWithData(body, "f", job, sep=sep, eol="\n", timeout=0)
    stats = _summarize(result)
    stats["expected"] = expected
    if stats.get("valid") != expected or stats.get("rejected"):
        raise RuntimeError(f"{job} {path.name}: {stats}\n{json.dumps(result)[:1500]}")
    return stats


def step_load(force: bool = False) -> None:
    state = {} if force else _state()
    for job, pattern in LOADS:
        for path in sorted(paths.PROCESSED.glob(pattern)):
            key = f"{job}:{path.name}"
            if key in state:
                log.info("skip %-44s (loaded %s)", key, state[key]["at"])
                continue
            start = time.time()
            stats = load_file(job, path)
            state[key] = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "secs": round(time.time() - start, 1), **stats}
            STATE.write_text(json.dumps(state, indent=2))
            log.info("loaded %-44s %s in %.0fs", key, stats, time.time() - start)


def _summarize(result) -> dict:
    """Valid/rejected line counts from a loading-job response (TigerGraph 4.x shape)."""
    file_level = result[0]["statistics"]["parsingStatistics"]["fileLevel"]
    rejected = sum(v for k, v in file_level.items() if k != "validLine" and isinstance(v, int))
    return {"valid": file_level.get("validLine", 0), "rejected": rejected}


# Vertices created from header rows by the first load (before headers were stripped).
HEADER_JUNK = {
    "Txn": ["tx_id", "from_tx", "to_tx"], "Card": ["card_id"], "Customer": ["customer_id"],
    "Holder": ["holder_id"], "DeviceProfile": ["device_id"], "Pattern": ["name", "pattern"],
    "ClosedCase": ["case_id"], "EmailDomain": ["p_email", "r_email"], "BillingRegion": ["region"],
}


def step_cleanup() -> None:
    conn = connection()
    for vtype, ids in HEADER_JUNK.items():
        deleted = conn.delVerticesById(vtype, ids)
        log.info("deleted %s header-row %s vertices", deleted, vtype)


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
    steps = ["all", "schema", "schema_changes", "jobs", "load", "cleanup", "queries", "status"]
    parser.add_argument("step", choices=steps)
    parser.add_argument("--force", action="store_true", help="reload files already marked loaded")
    parser.add_argument("--only", nargs="*", help="with `queries`: only these query names")
    args = parser.parse_args()
    steps = {
        "schema": [step_schema], "schema_changes": [step_schema_changes], "jobs": [step_jobs],
        "queries": [lambda: step_queries(args.only)],
        "load": [lambda: step_load(args.force)], "cleanup": [step_cleanup], "status": [step_status],
        "all": [step_schema, step_schema_changes, step_jobs, lambda: step_load(args.force),
                lambda: step_queries(None), step_status],
    }
    for fn in steps[args.step]:
        fn()


if __name__ == "__main__":
    sys.exit(main())
