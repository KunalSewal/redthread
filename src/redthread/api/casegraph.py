"""A case's evidence neighbourhood as nodes and edges for the dashboard, built from its trace.

Every node and edge carries the investigation ``step`` at which it became known, so the dashboard can
rewind the case and show only what the agent had seen by then. The step comes from the trace itself:
an event's ``detail`` is the ``ref`` of the evidence that produced it.
"""


def _steps_by_ref(trace: dict) -> dict[str, int]:
    """Which investigation step first produced each evidence ref."""
    out: dict[str, int] = {}
    for event in trace.get("events", []):
        ref = event.get("detail")
        if event.get("kind") == "evidence" and ref and ref not in out:
            try:
                out[ref] = int(event["step"])
            except (KeyError, TypeError, ValueError):
                continue
    return out


def case_graph(trace: dict, answer: dict | None) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    by_ref = _steps_by_ref(trace)
    current = {"step": 0}

    def at(source: dict | None) -> None:
        """Attribute everything created from here on to the step that produced ``source``."""
        current["step"] = by_ref.get((source or {}).get("ref", ""), current["step"])

    def node(nid: str, kind: str, label: str, **extra) -> None:
        if nid and nid not in nodes:
            nodes[nid] = {"id": nid, "kind": kind, "label": label, "step": current["step"], **extra}

    def edge(a: str, b: str, kind: str) -> None:
        if a in nodes and b in nodes and a != b:
            # An edge is only real once both ends are, so it appears at the later of the two.
            step = max(current["step"], nodes[a]["step"], nodes[b]["step"])
            edges.append({"source": a, "target": b, "kind": kind, "step": step})

    ev = trace.get("evidence", {})
    ctx = ev.get("alert_context", {})
    flagged = ctx.get("flagged_txn", {})
    card = ctx.get("card", {}).get("card_id")
    affected = set((answer or {}).get("case", {}).get("affected_txn_ids", []))
    connected = set((answer or {}).get("case", {}).get("connected_card_ids", []))

    at(ctx)
    node(ctx.get("customer_id"), "customer", ctx.get("customer_id", ""))
    node(card, "card", card or "", role="alert")
    edge(ctx.get("customer_id"), card, "owns")
    if flagged:
        node(flagged["tx_id"], "txn", f"${flagged['amount']:.2f}", role="flagged", ts=flagged["ts"],
             score=flagged.get("model_score"))
        edge(card, flagged["tx_id"], "made")
    at(ev.get("card_activity"))
    for row in ev.get("card_activity", {}).get("rows", []):
        if row["tx_id"] in affected and row["tx_id"] != flagged.get("tx_id"):
            node(row["tx_id"], "txn", f"${row['amount']:.2f}", role="affected", ts=row["ts"],
                 score=row.get("model_score"))
            edge(card, row["tx_id"], "made")
    at(ev.get("holder_baseline"))
    holder = ctx.get("holder")
    if holder:
        node(holder["holder_id"], "holder", f"holder ({holder['n_txns']} txns)")
        edge(flagged.get("tx_id"), holder["holder_id"], "by_holder")

    # Every device the agent examined: the flagged transaction's, and any it followed up on.
    for key, dev in ev.items():
        if not key.startswith("device_check"):
            continue
        at(dev)
        d = dev["device"]
        node(d["device_id"], "device", d["device_id"], profile=d["profile"], ring=d.get("ring_id"),
             cards_all_time=d["cards_all_time"])
        edge(card, d["device_id"], "used_device")
        edge(flagged.get("tx_id"), d["device_id"], "from_device")
        for c in dev["cards"][:18 if key == "device_check" else 8]:
            node(c["card_id"], "card", c["card_id"], role="connected" if c["card_id"] in connected else "neighbor",
                 score=c.get("max_model_score"))
            edge(c["card_id"], d["device_id"], "used_device")
        for cc in dev["closed_cases_on_device_all_time"]["cases"][:8]:
            node(cc["case_id"], "closed_case", cc["case_id"], outcome=cc["outcome"], pattern=cc["pattern"])
            node(cc["card_id"], "card", cc["card_id"], role="history")
            edge(cc["case_id"], cc["card_id"], "on_card")
            edge(cc["card_id"], d["device_id"], "used_device")

    at(ev.get("similar_cases"))
    for cid in (answer or {}).get("case", {}).get("similar_prior_cases", [])[:6]:
        hit = next((c for c in ev.get("similar_cases", {}).get("closed_cases", []) if c["case_id"] == cid), None)
        node(cid, "closed_case", cid, outcome=(hit or {}).get("outcome"), pattern=(hit or {}).get("pattern"))
        edge(card, cid, "similar_to")
    return {"nodes": list(nodes.values()), "edges": edges,
            "steps": max([n["step"] for n in nodes.values()] + [0])}
