"""Ablation: what each final-round answer would have been without the new detectors or the new priors.

    python scripts/ablation.py

No model call is needed. Each answer's probability is computed from its stored evidence ledger
(runs/<case>.trace.json) by redthread.belief.assess, so striking lines out and recomputing is exact:
the same function, the same ledger, the same subject IDs. Four variants per case:

- full: as submitted.
- no_detectors: the lines from new_kind_run, scheme_peers and recipient_cards struck out.
- old_priors: the bank-history prior (all 4,640 reports fraud; score bands from all transactions) and
  the January model score counted, as before this round.
- neither: both removed.

The pattern and episode also depend on the detectors (HHF-004's run of six, R9's undocumented name);
those are reported from the trace where they changed. Output: runs/ablation.json and a table.
"""

import json

from redthread import paths
from redthread.belief import Judged, assess
from redthread.data import sources

DETECTOR_REFS = ("query:new_kind_run(", "query:scheme_peers(", "query:recipient_cards(")


def posterior(trace: dict, drop_detectors: bool, old_priors: bool) -> float:
    belief, alert = trace["belief"], trace["alert"]
    refs = {e["claim"]: e["ref"] for e in trace["llm_assessment"]["evidence"]}
    kept = [Judged(basis=i["basis"], direction=i["direction"], strength=i["strength"], claim=i["claim"],
                   entities=tuple(i.get("entities") or ()))
            for i in belief["ledger"] if not (drop_detectors and refs.get(i["claim"], "").startswith(DETECTOR_REFS))]
    score = trace["evidence"]["alert_context"]["flagged_txn"].get("model_score")
    return assess(alert["trigger_type"], score, kept, frozenset(belief.get("subject") or ()),
                  None if old_priors else belief.get("as_of") or alert["opened_at"]).posterior


def main() -> None:
    rows = []
    for answer_path in sorted(sources.answers_dir().glob("HHF-*.json")):
        cid = answer_path.stem
        trace = json.loads((paths.ROOT / "runs" / f"{cid}.trace.json").read_text(encoding="utf-8"))
        answer = json.loads(answer_path.read_text(encoding="utf-8"))
        alert, lines = trace["alert"], trace["belief"]["ledger"]
        refs = {e["claim"]: e["ref"] for e in trace["llm_assessment"]["evidence"]}
        run = {k: posterior(trace, *flags) for k, flags in
               {"full": (False, False), "no_detectors": (True, False), "old_priors": (False, True),
                "neither": (True, True)}.items()}
        variants = run
        verdict = {k: "fraud" if p >= 0.85 else "legitimate" if p <= 0.15 else "uncertain" for k, p in variants.items()}
        detector_lines = sum(1 for i in lines if refs.get(i["claim"], "").startswith(DETECTOR_REFS))
        rows.append({"case": cid, "trigger": alert["trigger_type"], "submitted": answer["case"]["verdict"],
                     "pattern": answer["case"]["pattern"], "detector_lines": detector_lines,
                     "probability": {k: round(v, 3) for k, v in variants.items()}, "verdict": verdict})
    out = paths.ROOT / "runs" / "ablation.json"
    out.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print(f"{'case':8} {'trigger':16} {'full':>16} {'no detectors':>18} {'old priors':>18} {'neither':>18}")
    for r in rows:
        cells = [f"{r['verdict'][k][:5]} {r['probability'][k]:.2f}" for k in ("full", "no_detectors", "old_priors",
                                                                               "neither")]
        print(f"{r['case']:8} {r['trigger']:16} " + " ".join(f"{c:>18}" for c in cells))
    for k in ("full", "no_detectors", "old_priors", "neither"):
        counts = {v: sum(1 for r in rows if r["verdict"][k] == v) for v in ("fraud", "uncertain", "legitimate")}
        print(f"{k:13} {counts}")


if __name__ == "__main__":
    main()
