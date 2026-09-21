"""Export the graph-derived views the dashboard needs into data/processed, as files.

    python scripts/export_ui_data.py

The dashboard's ring and community pages would otherwise query TigerGraph on every request, which
ties the demo to a running workspace. Savanna's free tier auto-suspends, and the recording should not
depend on it, so these views are exported once and served from disk. Re-run after re-detecting rings
or re-running the community algorithm.

Writes data/processed/rings.json.
"""

import argparse
import json
import logging

from redthread import paths
from redthread.tg import GRAPH, connection

log = logging.getLogger("export_ui_data")
RINGS_OUT = paths.PROCESSED / "rings.json"


def _rows(result: list[dict], key: str) -> list[dict]:
    """Vertex rows from one PRINT, with the projection prefix stripped from attribute names."""
    for block in result:
        if key in block:
            return [{k.split(".", 1)[-1].lstrip("@"): v for k, v in row["attributes"].items()}
                    for row in block[key]]
    return []


def _scalar(result: list[dict], key: str):
    for block in result:
        if key in block:
            return block[key]
    return None


def export_rings(conn, k: int, members_for: int) -> dict:
    """Every ring, plus members and devices for the largest few."""
    top = conn.runInstalledQuery("top_rings", {"k": k}, timeout=120_000)
    cards = _scalar(top, "ring_cards") or {}
    devices = _scalar(top, "ring_devices") or {}
    rings = sorted(({"ring_id": int(rid), "cards": n, "devices": sorted(devices.get(rid, []))}
                    for rid, n in cards.items()), key=lambda r: r["cards"], reverse=True)
    log.info("%d rings; largest %s", len(rings), [r["cards"] for r in rings[:5]])

    # Members are only fetched for the rings the dashboard actually draws.
    for ring in rings[:members_for]:
        res = conn.runInstalledQuery("ring_members", {
            "ring_id": ring["ring_id"], "from_ts": "2016-01-01 00:00:00",
            "to_ts": "2017-01-01 00:00:00"}, timeout=120_000)
        ring["members"] = [{
            "card_id": m["card_id"], "txns": m.get("n_txns", 0),
            "max_model_score": None if (m.get("max_model_score") or -1) < 0 else round(m["max_model_score"], 4),
            "confirmed_fraud_closed_cases": sorted(m.get("closed_fraud_cases") or []),
            "agent_cases": sorted(m.get("agent_cases") or []),
        } for m in _rows(res, "members")]
        ring["device_profiles"] = [{"device_id": d["device_id"], "profile": d["profile"],
                                    "n_cards": d.get("n_cards")} for d in _rows(res, "devices")]
        log.info("ring %s: %d members, %d devices", ring["ring_id"], len(ring["members"]),
                 len(ring["device_profiles"]))

    summary = conn.runInstalledQuery("community_summary", {"k": 10, "min_cards": 5}, timeout=600_000)
    communities = _scalar(summary, "communities") or []
    return {
        "rings": rings,
        "communities": communities,
        "communities_total": _scalar(summary, "communities_total"),
        "communities_ranked": _scalar(summary, "communities_ranked"),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=40, help="how many rings to list")
    parser.add_argument("--members-for", type=int, default=12, help="how many rings to expand")
    args = parser.parse_args()
    conn = connection(GRAPH)
    data = export_rings(conn, args.k, args.members_for)
    RINGS_OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
    log.info("wrote %s", RINGS_OUT)


if __name__ == "__main__":
    main()
