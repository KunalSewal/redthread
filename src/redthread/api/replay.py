"""The regulator's view (challenge 6): an investigation replayed one step at a time from its trace.

Each step says what happened, which query ran with which parameters, what came back, which evidence
the agent held at that moment (and nothing collected later), and where its probability stood. The
probability exists from the assessment on; the step that sets it carries the full ledger, and the
step where a reply moved it says from what to what and why. Everything is read from the stored trace,
so the replay shows what the agent actually had, not a reconstruction of what it might have had.
"""

import re

_QUERY = re.compile(r"^query:(\w+)\((.*)\)$", re.S)


def _tool(ref: str) -> dict:
    m = _QUERY.match(ref or "")
    return {"query": m.group(1), "parameters": m.group(2)} if m else {"query": "", "parameters": ""}


def _summary(digest: dict) -> dict:
    """What came back, kept small: scalar fields whole, lists as their length and first few items."""
    out = {}
    for k, v in digest.items():
        if k == "ref":
            continue
        if isinstance(v, list):
            out[k] = {"count": len(v), "first": v[:3]}
        elif isinstance(v, dict):
            out[k] = {kk: vv for kk, vv in list(v.items())[:8]} if all(
                not isinstance(vv, (dict, list)) for vv in v.values()) else {"keys": sorted(v)[:12]}
        else:
            out[k] = v
    return out


def replay(trace: dict, answer: dict | None = None) -> dict:
    evidence = trace.get("evidence") or {}
    by_ref = {d.get("ref"): (k, d) for k, d in evidence.items() if isinstance(d, dict)}
    belief, final = trace.get("belief") or {}, trace.get("final_assessment") or {}
    held: list[str] = []
    probability = None
    steps = []
    for e in trace.get("events") or []:
        step = {"step": e["step"], "at": e.get("at"), "kind": e["kind"], "detail": e["detail"]}
        if e["kind"] == "evidence" and e["detail"] in by_ref:
            key, digest = by_ref[e["detail"]]
            held.append(e["detail"])
            step |= {"tool": key.split(":")[0], **_tool(e["detail"]), "returned": _summary(digest)}
        if e["kind"] == "assessment" and belief:
            probability = belief.get("posterior")
            step["belief"] = {"prior": belief.get("prior"), "prior_reason": belief.get("prior_reason"),
                              "posterior": probability, "verdict": belief.get("verdict"),
                              "how": belief.get("explanation"),
                              "counted": [{k: line[k] for k in ("basis", "direction", "strength", "lr", "claim")}
                                          for line in belief.get("ledger", []) if line.get("counted")]}
            step["moved"] = {"from": belief.get("prior"), "to": probability,
                             "because": "the judged evidence, combined as in the ledger"}
        if e["kind"] in ("reply", "final") and final.get("probability") is not None \
                and final["probability"] != probability:
            step["moved"] = {"from": probability, "to": final["probability"],
                             "because": (trace.get("reply") or {}).get("summary")
                             or (answer or {}).get("next_best_actions", {}).get("what_changed", "")}
            probability = final["probability"]
        step["evidence_held"] = list(held)
        step["probability"] = probability
        steps.append(step)
    return {"case_id": (trace.get("alert") or {}).get("case_id"), "steps": steps,
            "quarantined": trace.get("quarantine") or [],
            "final": {"verdict": final.get("verdict"), "probability": final.get("probability"),
                      "pattern": final.get("pattern")} if final else None}
