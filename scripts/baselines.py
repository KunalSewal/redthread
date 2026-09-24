"""How much of the agent's accuracy comes from the graph investigation, and how much from a score?

    python scripts/baselines.py --backtest runs/backtest_final.json --n 60 --month 10 --seed 909

Scores the same replayed closed cases the backtest used, three ways that involve no graph evidence
and no language model, and puts them next to the agent:

- the bank's legacy risk score on the flagged transaction, read through its own historical fraud rate;
- our fraud model's score on the flagged transaction, read the same way;
- the trigger alone: a customer report treated as fraud, a model alert as legitimate.

Each score becomes a verdict with the policy's own thresholds (fraud at 0.85 or above, legitimate at
0.15 or below, uncertain between), so all four are judged by the same rule. The calibration tables
are built only from months before the one replayed, as the backtest's are.

If the agent did no better than the model score, the investigation would be decoration. The gap
between them is what the graph and the reasoning over it are worth.
"""

import argparse
import json
import os
import sys

import pandas as pd

from redthread import paths
from redthread.model.calibration import MAX_MONTH_ENV

FRAUD_AT, LEGIT_AT = 0.85, 0.15
COST = {(True, "fraud"): 0.0, (True, "uncertain"): 0.3, (True, "legitimate"): 1.0,
        (False, "legitimate"): 0.0, (False, "uncertain"): 0.2, (False, "fraud"): 1.0}


def verdict(p: float) -> str:
    return "fraud" if p >= FRAUD_AT else "legitimate" if p <= LEGIT_AT else "uncertain"


def score(name: str, rows: list[tuple[bool, float, str]]) -> dict:
    """rows: (truly fraud, probability, verdict)."""
    n = len(rows)
    fraud = [r for r in rows if r[0]]
    cleared = [r for r in rows if not r[0]]
    ok = lambda r: (r[2] == "fraud") == r[0]  # noqa: E731 - same rule the backtest uses
    return {
        "method": name, "n": n,
        "verdict_accuracy": round(sum(ok(r) for r in rows) / n, 3),
        "fraud_caught": round(sum(ok(r) for r in fraud) / len(fraud), 3) if fraud else None,
        "cleared_left_alone": round(sum(ok(r) for r in cleared) / len(cleared), 3) if cleared else None,
        "brier": round(sum((r[1] - r[0]) ** 2 for r in rows) / n, 3),
        "cost": round(sum(COST[(r[0], r[2])] for r in rows) / n, 3),
        "wrongly_accused": sum(1 for r in cleared if r[2] == "fraud"),
        "missed_fraud": sum(1 for r in fraud if r[2] == "legitimate"),
        "uncertain": sum(1 for r in rows if r[2] == "uncertain"),
        # Stricter: the verdict itself matches, so an `uncertain` counts as a miss rather than as not accusing.
        "exact_verdicts": sum(1 for r in rows if r[2] == ("fraud" if r[0] else "legitimate")),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backtest", default="runs/backtest_final.json")
    parser.add_argument("--n", type=int, default=60)
    parser.add_argument("--month", type=int, default=10)
    parser.add_argument("--seed", type=int, default=909)
    args = parser.parse_args()

    os.environ[MAX_MONTH_ENV] = str(args.month - 1)  # calibrate only on earlier months
    from redthread.model.calibration import fraud_rate

    sys.path.insert(0, str(paths.ROOT / "scripts"))
    from backtest import build_alerts

    alerts = build_alerts(args.n, args.month, args.seed)
    scores = pd.read_csv(paths.PROCESSED / "txn_scores.csv").set_index("tx_id")["model_score"]
    risk = pd.read_parquet(paths.PROCESSED / "_all.parquet", columns=["tx_id", "risk_score"]) \
        .set_index("tx_id")["risk_score"]

    bank, model, trigger = [], [], []
    for a in alerts:
        truth = a["truth"]["outcome"] == "confirmed_fraud"
        tx = int(a["flagged_txn_id"])
        p_bank = fraud_rate(float(risk.get(tx, 0.5)), "risk_score") or 0.5
        p_model = fraud_rate(float(scores.get(tx, 0.0))) or 0.5
        p_trig = 0.97 if a["trigger_type"] == "customer_report" else 0.03
        bank.append((truth, p_bank, verdict(p_bank)))
        model.append((truth, p_model, verdict(p_model)))
        trigger.append((truth, p_trig, verdict(p_trig)))

    results = [score("bank risk score alone", bank), score("our fraud model alone", model),
               score("the alert type alone", trigger)]
    path = paths.ROOT / args.backtest
    if path.exists():
        cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
        agent = [(c["truth_outcome"] == "confirmed_fraud", c["probability"], c["verdict"]) for c in cases]
        results.append(score("RedThread agent (graph + reasoning)", agent))
        # The replay deals triggers at random, so it invents customer disputes of charges the analysts
        # cleared, a combination the bank's history never contains. Split exact verdicts by trigger so
        # the realistic stratum (model alerts) can be read on its own.
        model_by_case = dict(zip((a["case_id"] for a in alerts), model, strict=True))
        for method, rows in (("our fraud model alone", [model_by_case[c["case_id"]] for c in cases]),
                             ("RedThread agent (graph + reasoning)", agent)):
            entry = next(r for r in results if r["method"] == method)
            entry["exact_by_trigger"] = {
                t: [sum(1 for c, r in zip(cases, rows, strict=True) if c["trigger_type"] == t
                        and r[2] == ("fraud" if r[0] else "legitimate")),
                    sum(1 for c in cases if c["trigger_type"] == t)]
                for t in ("risk_score", "customer_report")}

    cols = ["method", "n", "verdict_accuracy", "cleared_left_alone", "fraud_caught", "brier",
            "wrongly_accused", "missed_fraud", "uncertain", "exact_verdicts"]
    print(pd.DataFrame(results)[cols].to_string(index=False))
    out = paths.PROCESSED / "baselines.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
