"""Containment plans for every ring the agent knows about (challenge 7).

    python scripts/containment.py                 # device rings + January schemes from the case traces
    python scripts/containment.py --penalty 500   # value acting against one legitimate person higher

Two sources of rings:

1. **Device rings** (data/processed/rings.json, from scripts/rings.py): cards joined through a device
   profile. The ring's exposure is what its cards spent through a ring device in the 90 days to the
   plan date. Blocking the device stops that on every card; blocking a card stops it on that card.
2. **January schemes** (runs/*.trace.json, scheme_peers and recipient_spike): cards that started the
   same new behaviour at once, or paid one recipient. With no shared device, only card blocks (and,
   for a recipient, declining payments to it) are possible.

Who an action touches, from the graph: blocking a card acts against the other people on it (holders
seen on the card in the 60 days before the ring window, minus those in the ring's own transactions),
because a card here is an issuer bucket, not one person; blocking a device acts against the customers
of non-ring cards that used it; declining a recipient acts against cards that paid it in the two
months before the spike. Output: data/processed/containment.json, every amount and person listed.
"""

import argparse
import json
import logging
from datetime import datetime, timedelta

from redthread import paths
from redthread.containment import DEFAULT_PENALTY_USD, Action, Item, block_everything, plan
from redthread.tg import GRAPH, connection

log = logging.getLogger("containment")
PLAN_AT = "2017-02-01 00:00:00"  # the end of the data: plans are made as of the latest activity
TS = "%Y-%m-%d %H:%M:%S"
OUT = paths.PROCESSED / "containment.json"


def _attrs(vertices: list[dict]) -> list[dict]:
    return [{k.split(".", 1)[-1].lstrip("@"): v for k, v in x["attributes"].items()} for x in vertices]


def _shift(ts: str, days: int) -> str:
    return (datetime.strptime(ts[:19], TS) - timedelta(days=days)).strftime(TS)


class Graph:
    def __init__(self):
        self.conn = connection(GRAPH)
        self.queries: list[dict] = []

    def run(self, name: str, **params) -> list:
        self.queries.append({"query": name, "params": params})
        return self.conn.runInstalledQuery(name, params)

    def card_txns(self, card: str, lo: str, hi: str) -> list[dict]:
        return _attrs(self.run("card_window", card=card, from_ts=lo, to_ts=hi, as_of=PLAN_AT)[0]["txns"])

    def people_on_card(self, card: str, before: str, exclude: set[str]) -> set[str]:
        rows = self.card_txns(card, _shift(before, 60), before)
        return {r["holder_id"] for r in rows if r.get("holder_id")} - exclude


def device_ring(g: Graph, ring: dict) -> dict:
    hi, lo = PLAN_AT, _shift(PLAN_AT, 90)
    devices = set(ring["devices"])
    items, card_rows = [], {}
    for m in ring["members"]:
        rows = g.card_txns(m["card_id"], lo, hi)
        card_rows[m["card_id"]] = rows
        items += [Item(r["tx_id"], m["card_id"], float(r["amount"]), frozenset({f"device:{r['device_id']}"}))
                  for r in rows if r.get("device_id") in devices]
    ring_holders = {r["holder_id"] for rows in card_rows.values() for r in rows
                    if r.get("device_id") in devices and r.get("holder_id")}
    start = min((r["ts"] for rows in card_rows.values() for r in rows if r.get("device_id") in devices), default=lo)
    candidates = [Action("card", c, frozenset(g.people_on_card(c, start, ring_holders))) for c in card_rows]
    members = set(card_rows)
    for d in devices:
        res = g.run("device_neighbors", device=d, from_ts=lo, to_ts=hi, as_of=PLAN_AT)
        others = {c["card_id"].split("-")[0] for c in _attrs(res[1]["cards"]) if c["card_id"] not in members}
        candidates.append(Action("device", f"device:{d}", frozenset(others)))
    return {"ring": f"device ring {ring['ring_id']}", "shared": sorted(devices), "cards": sorted(members),
            "items": items, "candidates": candidates}


def scheme_rings(g: Graph) -> list[dict]:
    """One ring per distinct January scheme found in the traces (the same scheme seen from several
    cases is planned once)."""
    out, seen = [], set()
    for trace_path in sorted((paths.ROOT / "runs").glob("HHF-*.trace.json")):
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        ev = trace.get("evidence") or {}
        alert_card = trace["alert"]["card_id"]
        for key, kind in (("scheme_peers", "scheme"), ("recipient_spike", "recipient")):
            d = ev.get(key)
            if not d or not d.get("strength"):
                continue
            label = d.get("signature") or f"recipient {d.get('recipient_email')}"
            if label in seen:
                continue
            seen.add(label)
            peers = d.get("peers") or d.get("cards") or []
            via = frozenset({f"recipient:{d['recipient_email']}"}) if kind == "recipient" else frozenset()
            items = [Item(f"{p['card_id']}:{','.join(p['tx_ids'])}", p["card_id"], float(p["amount"]), via)
                     for p in peers]
            run = (ev.get("activity_shift") or {}).get("run") or []
            items += [Item(r["tx_id"], alert_card, abs(float(r["amount"])), via) for r in run]
            cards = sorted({i.card_id for i in items})
            started = min([p.get("first_ts", PLAN_AT) for p in peers] + [r["ts"] for r in run] or [PLAN_AT])
            candidates = [Action("card", c, frozenset(g.people_on_card(c, started, set()))) for c in cards]
            if kind == "recipient":
                res = g.run("recipient_cards", domain=d["recipient_email"], from_ts=_shift(started, 90),
                            to_ts=_shift(started, 30), as_of=PLAN_AT)
                regular = {c["customer_id"] for c in _attrs(res[1]["cards"]) if c["card_id"] not in cards}
                candidates.append(Action("recipient", f"recipient:{d['recipient_email']}", frozenset(regular)))
            out.append({"ring": f"{kind}: {label}", "found_in": trace["alert"]["case_id"], "shared": [label],
                        "cards": cards, "items": items, "candidates": candidates})
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser()
    parser.add_argument("--penalty", type=float, default=DEFAULT_PENALTY_USD)
    args = parser.parse_args()
    g = Graph()
    rings = [device_ring(g, r) for r in json.loads((paths.PROCESSED / "rings.json").read_text())["rings"]]
    rings += scheme_rings(g)
    plans = []
    for r in rings:
        best = plan(r["items"], r["candidates"], args.penalty)
        naive = block_everything(r["items"], r["candidates"], args.penalty)
        plans.append({k: r[k] for k in ("ring", "shared", "cards") if k in r} | {
            "found_in": r.get("found_in", ""), "transactions": len(r["items"]),
            "plan": best.as_dict(), "block_every_card": naive.as_dict(),
            "candidate_touches": {f"{a.kind}:{a.target}": len(a.touches) for a in r["candidates"]}})
        log.info("%-60s cut $%9.2f of $%9.2f touching %3d (blocking every card: $%9.2f touching %3d) via %s",
                 r["ring"][:60], best.exposure_cut, best.exposure_total, len(best.customers_touched),
                 naive.exposure_cut, len(naive.customers_touched),
                 ", ".join(f"{a.kind}:{a.target}" for a in best.actions)[:80])
    OUT.write_text(json.dumps({"planned_as_of": PLAN_AT, "made_at": datetime.now().isoformat(timespec="seconds"),
                               "penalty_usd_per_person": args.penalty, "plans": plans,
                               "queries": g.queries}, indent=1), encoding="utf-8")
    log.info("wrote %s (%d plans, %d queries)", OUT, len(plans), len(g.queries))


if __name__ == "__main__":
    main()
