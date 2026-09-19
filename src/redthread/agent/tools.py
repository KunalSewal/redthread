"""Investigation tools: installed GSQL queries (via MCP) turned into compact, citable evidence.

Each tool returns a digest the LLM can reason over (not raw rows), tagged with a ``ref`` that
evidence claims must cite. Every transaction, card, device and case ID a tool returns is recorded
in ``Ledger`` so the agent's conclusions can be checked against what it actually saw.
"""

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from redthread.agent.mcp_graph import GraphToolError, McpGraph
from redthread.model.calibration import fraud_rate, hot_share
from redthread.rag.embed import embed_query

TS_FMT = "%Y-%m-%d %H:%M:%S"
HOT_SCORE = 0.5
SMALL_AUTH_USD = 10.0
MAX_ROWS = 70
GENERIC_DEVICE_INFO = {"iOS Device", "MacOS", "Windows", "Trident/7.0", "Linux", "SAMSUNG", "unknown"}


@dataclass
class Ledger:
    """Everything the tools have shown the agent."""

    txns: dict[str, dict] = field(default_factory=dict)  # tx_id -> compact row (has amount, ts)
    cards: set[str] = field(default_factory=set)
    devices: dict[str, str] = field(default_factory=dict)  # device_id -> profile
    closed_cases: dict[str, dict] = field(default_factory=dict)
    agent_cases: set[str] = field(default_factory=set)
    refs: dict[str, str] = field(default_factory=dict)  # ref -> tool name

    def entity_known(self, entity_id: str) -> bool:
        return (entity_id in self.txns or entity_id in self.cards or entity_id in self.devices
                or entity_id in self.closed_cases or entity_id in self.agent_cases
                or entity_id in self.devices.values()
                or entity_id.split("-")[0] in {c.split("-")[0] for c in self.cards})


def _ts(value: str) -> datetime:
    return datetime.strptime(value[:19], TS_FMT)


def _fmt(value: datetime) -> str:
    return value.strftime(TS_FMT)


def _attrs(vertices: list[dict], prefix: str = "") -> list[dict]:
    """Vertex list -> attribute dicts, with 'set.' prefixes from projected PRINTs stripped."""
    out = []
    for v in vertices:
        attrs = {k.split(".", 1)[-1].lstrip("@"): val for k, val in v["attributes"].items()}
        attrs.setdefault("id", v.get("v_id"))
        out.append(attrs)
    return out


def _score(value) -> float | None:
    return None if value is None or value < 0 else round(float(value), 3)


class Tools:
    def __init__(self, graph: McpGraph):
        self.g = graph
        self.ledger = Ledger()

    async def _q(self, name: str, **params) -> list[dict]:
        return await self.g.query(name, params)

    def _ref(self, tool: str, text: str) -> str:
        ref = f"query:{text}"
        self.ledger.refs[ref] = tool
        return ref

    def _txn_row(self, a: dict) -> dict:
        row = {
            "tx_id": a["tx_id"], "ts": a["ts"], "amount": a["amount"], "product": a["product_cd"],
            "channel": a["channel"], "region": a.get("region") or None, "holder_id": a.get("holder_id"),
            "device_id": a.get("device_id") or None, "device_status": a.get("device_status") or None,
            "proxy": a.get("proxy_type") or None, "p_email": a.get("p_email") or None,
            "r_email": a.get("r_email") or None, "risk_score": a.get("risk_score"),
            "model_score": _score(a.get("model_score")),
        }
        if row["model_score"] is not None:
            row["model_hist_fraud_rate"] = fraud_rate(row["model_score"])
        for key in ("closed_cases", "agent_cases"):
            if a.get(key):
                row[key] = sorted(a[key])
        m_flags = {k: a[k] for k in ("m4", "m6") if a.get(k)}
        if m_flags:
            row["match_flags"] = m_flags
        self.ledger.txns[row["tx_id"]] = row
        return row

    # ------------------------------------------------------------------ core evidence
    async def alert_context(self, tx_id: str) -> dict:
        res = await self._q("alert_context", tx=tx_id)
        top = res[0]
        flagged = self._txn_row(_attrs(top["flagged"])[0])
        card = _attrs(top["card"])[0]
        cards = [c["card_id"] for c in _attrs(top["customer_cards"])]
        self.ledger.cards.update(cards)
        device = _attrs(top["device"])
        holder = _attrs(top["holder"])
        prior = sorted(_attrs(res[1]["prior_closed_cases"]), key=lambda c: c["opened_at"], reverse=True)
        for c in prior:
            self.ledger.closed_cases[c["case_id"]] = c
        agent = _attrs(res[2]["prior_agent_cases"])
        self.ledger.agent_cases.update(c["case_id"] for c in agent)
        out = {
            "ref": self._ref("alert_context", f"alert_context(tx={tx_id})"),
            "flagged_txn": flagged,
            "card": {"card_id": card["card_id"], "network": card.get("card4"), "type": card.get("card6"),
                     "ring_id": card.get("ring_id"), "ring_size": card.get("ring_size")},
            "customer_id": card["customer_id"],
            "customer_cards": cards,
            "note": ("customer_id is an issuer bucket shared by many account holders; judge normal behaviour "
                     "at the holder level (holder_id), not the card or customer level"),
        }
        if holder:
            out["holder"] = {k: holder[0][k] for k in ("holder_id", "n_txns", "first_ts", "last_ts", "amount_mean")}
        if device:
            out["device"] = self._device_summary(device[0])
        out["prior_closed_cases_on_customer_cards"] = {
            "count": len(prior),
            "by_outcome": _count(c["outcome"] for c in prior),
            "by_pattern": _count(c["pattern"] for c in prior),
            "most_recent": [_case_row(c) for c in prior[:8]],
        }
        if agent:
            out["prior_agent_cases"] = agent
        return out

    def _device_summary(self, d: dict) -> dict:
        self.ledger.devices[d["device_id"]] = d["profile"]
        generic = (d.get("device_info") or "unknown") in GENERIC_DEVICE_INFO or not d.get("screen")
        return {"device_id": d["device_id"], "profile": d["profile"], "cards_all_time": d["n_cards"],
                "profile_specificity": "generic (shared by many unrelated people)" if generic else "specific",
                "ring_id": d.get("ring_id"), "ring_cards": d.get("ring_size")}

    async def card_activity(self, card_id: str, center_ts: str, days_before: int = 10, days_after: int = 3,
                            flagged_tx: str | None = None) -> dict:
        center = _ts(center_ts)
        lo, hi = center - timedelta(days=days_before), center + timedelta(days=days_after)
        res = await self._q("card_window", card=card_id, from_ts=_fmt(lo), to_ts=_fmt(hi))
        rows = sorted((self._txn_row(a) for a in _attrs(res[0]["txns"])), key=lambda r: r["ts"])
        self.ledger.cards.add(card_id)
        flagged_holder = self.ledger.txns.get(flagged_tx, {}).get("holder_id") if flagged_tx else None
        suspicious = [r for r in rows if (r["model_score"] or 0) >= 0.3 or r["proxy"] or r.get("closed_cases")]
        near = [r for r in rows if abs((_ts(r["ts"]) - center).total_seconds()) <= 48 * 3600]
        same_holder = [r for r in rows if flagged_holder and r["holder_id"] == flagged_holder]
        keep = {r["tx_id"] for r in suspicious + near + same_holder}
        shown = [r for r in rows if r["tx_id"] in keep] if len(rows) > MAX_ROWS else rows
        return {
            "ref": self._ref("card_activity", f"card_window(card={card_id}, {lo:%Y-%m-%d}..{hi:%Y-%m-%d})"),
            "card_id": card_id, "window": [_fmt(lo), _fmt(hi)], "n_txns": len(rows),
            "n_holders": len({r["holder_id"] for r in rows}),
            "channels": _count(r["channel"] for r in rows),
            "suspicious_txns": [r["tx_id"] for r in suspicious],
            "card_testing_sequences": _card_testing(rows),
            "shown_rows": len(shown),
            "rows": shown if len(shown) <= 120 else shown[:120],
            "omitted_note": ("rows limited to suspicious, within 48h of the alert, or same holder"
                             if len(shown) < len(rows) else ""),
        }

    async def holder_baseline(self, holder_id: str, flagged_tx: str) -> dict:
        flagged = self.ledger.txns[flagged_tx]
        res = await self._q("holder_history", holder=holder_id, before_ts=flagged["ts"])
        summary, rows = res[0], [self._txn_row({**a, "holder_id": holder_id}) for a in _attrs(res[1]["txns"])]
        n = summary["n_txns"]
        similar = [r for r in rows if r["product"] == flagged["product"] and flagged["amount"]
                   and abs(r["amount"] - flagged["amount"]) / flagged["amount"] <= 0.05]
        dates = sorted(_ts(r["ts"]) for r in similar)
        gaps = [round((b - a).total_seconds() / 86400, 1) for a, b in zip(dates, dates[1:], strict=False)]
        if dates:
            gaps.append(round((_ts(flagged["ts"]) - dates[-1]).total_seconds() / 86400, 1))
        recurring = _regular(gaps)
        return {
            "ref": self._ref("holder_baseline", f"holder_history(holder={holder_id}, before={flagged['ts'][:10]})"),
            "holder_id": holder_id,
            "prior_txns": n,
            "first_seen": summary.get("first_ts") if n else None,
            "amount_mean": round(summary["amount_sum"] / n, 2) if n else None,
            "amount_max": summary["amount_max"] if n else None,
            "regions": summary["regions"], "products": summary["products"], "channels": summary["channels"],
            "devices_seen": summary["devices"],
            "flagged_is_new_for_holder": {
                "first_txn_of_holder": n == 0,
                "region": bool(n) and flagged["region"] is not None and flagged["region"] not in summary["regions"],
                "product": bool(n) and flagged["product"] not in summary["products"],
                "device": bool(n) and flagged["device_id"] is not None
                and flagged["device_id"] not in summary["devices"],
                "amount_above_prior_max": bool(n) and flagged["amount"] > summary["amount_max"] * 1.5,
            },
            "similar_amount_same_product": [{"tx_id": r["tx_id"], "ts": r["ts"], "amount": r["amount"]}
                                            for r in sorted(similar, key=lambda r: r["ts"])][-8:],
            "days_between_similar_charges": gaps[-8:],
            "recurring_pattern": recurring,
            "recent_txns": rows[:15],
        }

    async def device_check(self, device_id: str, center_ts: str, days: int = 30) -> dict:
        center = _ts(center_ts)
        lo, hi = center - timedelta(days=days), center + timedelta(days=3)
        res = await self._q("device_neighbors", device=device_id, from_ts=_fmt(lo), to_ts=_fmt(hi))
        device = self._device_summary(_attrs(res[0]["device"])[0])
        cards = _attrs(res[1]["cards"])
        self.ledger.cards.update(c["card_id"] for c in cards)
        for c in cards:
            c["max_model_score"] = _score(c.pop("max_model_score", None))
        cases = [dict(zip(("case_id", "card_id", "outcome", "pattern", "opened"), s.split("|"), strict=True))
                 for s in res[2]["closed_cases_on_device"]]
        for c in cases:
            self.ledger.closed_cases.setdefault(c["case_id"], c)
        agent = _attrs(res[3]["agent_cases"])
        self.ledger.agent_cases.update(a["case_id"] for a in agent)
        ranked = sorted(cards, key=lambda c: (-(c["max_model_score"] or 0), c["card_id"]))
        return {
            "ref": self._ref("device_check", f"device_neighbors(device={device_id}, {lo:%Y-%m-%d}..{hi:%Y-%m-%d})"),
            "device": device,
            "window": [_fmt(lo), _fmt(hi)],
            "cards_in_window": len(cards),
            "cards_new_device_in_window": sum(1 for c in cards if c["new_device"]),
            "cards_behind_proxy_in_window": sum(1 for c in cards if c["proxy"]),
            "cards_with_model_score_over_0.5": sum(1 for c in cards if (c["max_model_score"] or 0) >= HOT_SCORE),
            "cards": [{k: c[k] for k in ("card_id", "n_txns", "amount", "max_model_score", "new_device", "proxy",
                                         "first_ts", "last_ts", "ring_id")} | {"tx_ids": sorted(c["tx_ids"])[:6]}
                      for c in ranked[:25]],
            "closed_cases_on_device_all_time": {"count": len(cases), "by_pattern": _count(c["pattern"] for c in cases),
                                                "cases": cases[:12]},
            "agent_cases_on_device": agent,
        }

    async def shared_origin(self, tx_id: str, window_days: int = 7) -> dict:
        res = await self._q("shared_origin", tx=tx_id, window_days=window_days, score_min=HOT_SCORE)
        n_txns, n_hot = res[1]["n_txns"], res[1]["n_hot_txns"]
        hot_cards, cards, cases = res[2]["hot_cards"], res[3]["cards"], res[2]["agent_fraud_cases"]
        baseline = hot_share(HOT_SCORE)
        elements = []
        for el, n in sorted(n_txns.items()):
            hot = n_hot.get(el, 0)
            self.ledger.cards.update(hot_cards.get(el, []))
            elements.append({
                "element": el, "txns_in_window": n, "cards_in_window": len(cards.get(el, [])),
                "txns_model_over_0.5": hot, "cards_model_over_0.5": sorted(hot_cards.get(el, []))[:20],
                "hot_share": round(hot / n, 4) if n else 0,
                "lift_vs_all_txns": round(hot / n / baseline, 2) if n else 0,
                "agent_fraud_cases": sorted(cases.get(el, [])),
            })
        return {
            "ref": self._ref("shared_origin", f"shared_origin(tx={tx_id}, window=+/-{window_days}d)"),
            "window": [res[0]["window_from"], res[0]["window_to"]],
            "baseline_hot_share_all_txns": round(baseline, 4),
            "elements": elements,
            "how_to_read": ("lift = share of transactions on this element scoring >= 0.5, divided by the same "
                            "share across all transactions. Large regions and common email domains carry many "
                            "unrelated cards; a shared origin needs lift well above 1 and several distinct cards."),
        }

    async def linked_cases(self, tx_id: str) -> dict:
        res = await self._q("linked_cases", tx=tx_id)
        closed = _attrs(res[0]["closed"])
        for c in closed:
            self.ledger.closed_cases[c["case_id"]] = c
        agent = _attrs(res[1]["agent"])
        self.ledger.agent_cases.update(a["case_id"] for a in agent)
        closed = sorted(closed, key=lambda c: c["opened_at"], reverse=True)
        return {
            "ref": self._ref("linked_cases", f"linked_cases(tx={tx_id})"),
            "closed_cases": [_case_row(c) | {"linked_via": sorted(c["via"])} for c in closed[:15]],
            "closed_cases_total": len(closed),
            "agent_cases": agent,
        }

    async def similar_cases(self, description: str, k: int = 6) -> dict:
        qv = embed_query(description)
        res = await self._q("similar_closed_cases", qv=qv, k=k)
        hits = _attrs(res[0]["hits"])
        devices = res[1]["case_devices"]
        for h in hits:
            self.ledger.closed_cases[h["case_id"]] = h
        out = {
            "ref": self._ref("similar_cases", f"similar_closed_cases(\"{description[:60]}...\", k={k})"),
            "closed_cases": [_case_row(h) | {"devices": devices.get(h["case_id"], [])} for h in hits],
        }
        try:
            agent = await self._q("similar_fraud_cases", qv=qv, k=3)
            out["agent_cases"] = _attrs(agent[0]["hits"])
            self.ledger.agent_cases.update(a["case_id"] for a in out["agent_cases"])
        except GraphToolError:
            out["agent_cases"] = []  # no agent cases with vectors yet
        return out

    async def ring(self, ring_id: int, center_ts: str, days: int = 45) -> dict:
        center = _ts(center_ts)
        lo, hi = center - timedelta(days=days), center + timedelta(days=days)
        res = await self._q("ring_members", ring_id=ring_id, from_ts=_fmt(lo), to_ts=_fmt(hi))
        members = _attrs(res[0]["members"])
        devices = _attrs(res[1]["devices"])
        self.ledger.cards.update(m["card_id"] for m in members)
        for d in devices:
            self.ledger.devices[d["device_id"]] = d["profile"]
        return {
            "ref": self._ref("ring", f"ring_members(ring={ring_id})"),
            "ring_id": ring_id,
            "definition": ("cards linked through a specific device that was new to each account in a suspicious "
                           "transaction (confirmed fraud or model score >= 0.5); connected components via GSQL"),
            "devices": devices,
            "members": [{"card_id": m["card_id"], "txns_in_window": m["n_txns"],
                         "max_model_score": _score(m["max_model_score"]),
                         "confirmed_fraud_closed_cases": sorted(m["closed_fraud_cases"]),
                         "agent_cases": sorted(m["agent_cases"])} for m in members],
        }

    async def policy(self, question: str, k: int = 4) -> dict:
        res = await self._q("policy_search", qv=embed_query(question), k=k)
        hits = _attrs(res[0]["hits"])
        return {
            "ref": self._ref("policy", f"policy_search(\"{question[:60]}\")"),
            "passages": [{"chunk_id": h["chunk_id"], "section": h["section"], "text": h["content"][:1200]}
                         for h in hits],
        }


def _count(values) -> dict:
    out: dict = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _case_row(c: dict) -> dict:
    keep = ("case_id", "card_id", "opened_at", "outcome", "pattern", "n_txns", "exposure_usd", "analyst_notes")
    return {k: c[k] for k in keep if k in c}


def _card_testing(rows: list[dict]) -> list[dict]:
    """R5: three or more small online authorizations within an hour, then a larger purchase."""
    online = [r for r in rows if r["channel"] == "online"]
    found, used = [], set()
    for i, r in enumerate(online):
        if r["amount"] >= SMALL_AUTH_USD or r["tx_id"] in used:
            continue
        start = _ts(r["ts"])
        small = [x for x in online[i:] if x["amount"] < SMALL_AUTH_USD and _ts(x["ts"]) - start <= timedelta(hours=1)]
        if len(small) < 3:
            continue
        last = _ts(small[-1]["ts"])
        larger = [x for x in online if last < _ts(x["ts"]) <= last + timedelta(hours=24) and x["amount"] >= 3 * max(
            s["amount"] for s in small) and x["amount"] >= SMALL_AUTH_USD]
        if larger:
            used.update(x["tx_id"] for x in small)
            found.append({"small_auths": [x["tx_id"] for x in small], "followed_by": [x["tx_id"] for x in larger[:3]],
                          "purchase_over_100_cleared": any(x["amount"] > 100 for x in larger)})
    return found


def _regular(gaps: list[float]) -> dict:
    """Is a charge recurring? Needs at least two prior similar charges at a steady interval."""
    if len(gaps) < 2:
        return {"recurring": False, "reason": "fewer than two prior similar charges"}
    median = statistics.median(gaps)
    spread = max(abs(g - median) for g in gaps[-4:])
    for label, lo, hi in (("weekly", 5, 9), ("fortnightly", 12, 16), ("monthly", 26, 35)):
        if lo <= median <= hi and spread <= max(3, median * 0.25):
            return {"recurring": True, "cadence": label, "median_days": median}
    return {"recurring": False, "median_days": median, "reason": "intervals are not steady"}
