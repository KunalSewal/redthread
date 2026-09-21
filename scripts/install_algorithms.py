"""Install and run TigerGraph's GDS library algorithms over the card <-> device projection.

    python scripts/install_algorithms.py            # fetch, install, run, report
    python scripts/install_algorithms.py --show     # print installed signatures and exit
    python scripts/install_algorithms.py --run-only # skip install, just run

The GSQL comes from TigerGraph's own library (github.com/tigergraph/gsql-graph-algorithms), fetched
by path from its manifest, so these are the library implementations rather than ours. pyTigerGraph's
featurizer would normally do this, but it builds the URL with an OS path separator and 404s on
Windows, so we fetch and install directly — which also makes the provenance explicit.

- tg_louvain: communities in the card/device graph (who moves together), weighted by how many
  transactions tie a card to a device
- tg_jaccard_nbor_ss: neighbour similarity, run per card for entity resolution (which other cards
  behave like this one), called on demand by the agent rather than in batch
- tg_pagerank is installed but not run in batch: this release takes a single vertex type, and our
  projection is bipartite (cards and devices). Device centrality is already stored as
  DeviceProfile.n_cards, which is the quantity PageRank would approximate here.

Our own ring_wcc stays: it is tuned to suspicious, new-to-account device use and is measured. These
add structure on top of it.
"""

import argparse
import json
import logging
import sys
import urllib.request

from redthread import paths
from redthread.tg import GRAPH, connection

sys.path.insert(0, str(paths.ROOT / "scripts"))
from setup_graph import GsqlError, gsql  # noqa: E402

log = logging.getLogger("install_algorithms")

REPO = "https://raw.githubusercontent.com/tigergraph/gsql-graph-algorithms/master"
ALGORITHMS = {
    "tg_louvain": "algorithms/Community/louvain/tg_louvain.gsql",
    "tg_pagerank": "algorithms/Centrality/pagerank/global/unweighted/tg_pagerank.gsql",
    "tg_jaccard_nbor_ss": "algorithms/Similarity/jaccard/single_source/tg_jaccard_nbor_ss.gsql",
}
# The projection the algorithms run on: cards joined to the devices they used.
VERTEX_TYPES = ["Card", "DeviceProfile"]
EDGE_TYPES = ["USED_DEVICE", "DEVICE_CARD"]


def fetch(path: str) -> str:
    return urllib.request.urlopen(f"{REPO}/{path}", timeout=60).read().decode("utf-8")


def install() -> list[str]:
    installed = []
    for name, path in ALGORITHMS.items():
        body = fetch(path).replace("@graph@", GRAPH).replace("CREATE QUERY", "CREATE OR REPLACE QUERY", 1)
        try:
            gsql(body)
            installed.append(name)
            log.info("created %s from %s", name, path)
        except GsqlError as exc:
            log.warning("could not create %s: %s", name, str(exc)[:300])
    if installed:
        log.info("installing %s (compiles, takes a few minutes)", ", ".join(installed))
        log.info("%s", gsql(f"INSTALL QUERY {', '.join(installed)}")[-300:])
    return installed


def signatures(conn, names) -> dict[str, dict]:
    """Parameter names and types of each installed algorithm, straight from the server."""
    out = {}
    for name in names:
        try:
            meta = conn.getQueryMetadata(name)
            out[name] = {p["paramName"]: p.get("paramType", "?") for p in meta.get("parameters", [])}
        except Exception as exc:
            out[name] = {"error": str(exc)[:160]}
    return out


def build_params(available: dict[str, str], wanted: dict[str, object]) -> dict:
    """Keep only the parameters this version of the algorithm declares (names vary by release)."""
    return {k: v for k, v in wanted.items() if k in available}


def run(conn) -> dict:
    """Run the batch algorithm. Parameter names come from the library's own signature, which varies
    by release, so they are passed exactly as tg_louvain declares them."""
    params = {
        "v_type_set": VERTEX_TYPES,
        "e_type_set": EDGE_TYPES,
        # How many transactions tie this card to this device: a real weight, not a placeholder.
        "weight_attribute": "n_txns",
        "maximum_iteration": 10,
        "result_attribute": "community_id",
        "file_path": "",
        "print_stats": True,
    }
    log.info("running tg_louvain %s", json.dumps(params))
    result = conn.runInstalledQuery("tg_louvain", params, timeout=1_800_000)
    log.info("tg_louvain done")
    return {"tg_louvain": result}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", action="store_true", help="print installed signatures and exit")
    parser.add_argument("--run-only", action="store_true", help="skip installation")
    args = parser.parse_args()
    conn = connection(GRAPH)

    if not (args.show or args.run_only):
        install()
    sigs = signatures(conn, ALGORITHMS)
    log.info("signatures: %s", json.dumps(sigs, indent=1))
    if args.show:
        return

    results = run(conn)
    (paths.PROCESSED / "gds_run.json").write_text(json.dumps(
        {"signatures": sigs, "results": {k: str(v)[:500] for k, v in results.items()}}, indent=2))
    log.info("wrote data/processed/gds_run.json")


if __name__ == "__main__":
    main()
