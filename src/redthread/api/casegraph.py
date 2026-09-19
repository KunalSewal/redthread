"""A case's evidence neighbourhood as nodes and edges for the dashboard, built from its trace."""


def case_graph(trace: dict, answer: dict | None) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def node(nid: str, kind: str, label: str, **extra) -> None:
        if nid and nid not in nodes:
            nodes[nid] = {"id": nid, "kind": kind, "label": label, **extra}

    def edge(a: str, b: str, kind: str) -> None:
        if a in nodes and b in nodes and a != b:
            edges.append({"source": a, "target": b, "kind": kind})

    ev = trace.get("evidence", {})
    ctx = ev.get("alert_context", {})
    flagged = ctx.get("flagged_txn", {})
    card = ctx.get("card", {}).get("card_id")
    affected = set((answer or {}).get("case", {}).get("affected_txn_ids", []))
    connected = set((answer or {}).get("case", {}).get("connected_card_ids", []))

    node(ctx.get("customer_id"), "customer", ctx.get("customer_id", ""))
    node(card, "card", card or "", role="alert")
    edge(ctx.get("customer_id"), card, "owns")
    if flagged:
        node(flagged["tx_id"], "txn", f"${flagged['amount']:.2f}", role="flagged", ts=flagged["ts"],
             score=flagged.get("model_score"))
        edge(card, flagged["tx_id"], "made")
    for row in ev.get("card_activity", {}).get("rows", []):
        if row["tx_id"] in affected and row["tx_id"] != flagged.get("tx_id"):
            node(row["tx_id"], "txn", f"${row['amount']:.2f}", role="affected", ts=row["ts"],
                 score=row.get("model_score"))
            edge(card, row["tx_id"], "made")
    holder = ctx.get("holder")
    if holder:
        node(holder["holder_id"], "holder", f"holder ({holder['n_txns']} txns)")
        edge(flagged.get("tx_id"), holder["holder_id"], "by_holder")

    # Every device the agent examined: the flagged transaction's, and any it followed up on.
    for key, dev in ev.items():
        if not key.startswith("device_check"):
            continue
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

    for cid in (answer or {}).get("case", {}).get("similar_prior_cases", [])[:6]:
        hit = next((c for c in ev.get("similar_cases", {}).get("closed_cases", []) if c["case_id"] == cid), None)
        node(cid, "closed_case", cid, outcome=(hit or {}).get("outcome"), pattern=(hit or {}).get("pattern"))
        edge(card, cid, "similar_to")
    return {"nodes": list(nodes.values()), "edges": edges}
