"""Fit how much the evidence ledger's likelihood ratios are really worth.

    python scripts/fit_aggregation.py --backtest runs/backtest_60.json

The ledger multiplies one likelihood ratio per independent basis. With six or seven bases pointing
the same way that product saturates, and the 60-case backtest showed what that costs: a Brier score
of 0.36, which is worse than always guessing the base rate, because the wrong answers are given at
0.97. Bases are not really independent -- device, holder behaviour, region and timing all move
together in a real fraud -- and naive multiplication over correlated evidence is the classic way to
become overconfident.

So the aggregate is tempered:

    logit(posterior) = logit(prior) + alpha * sum(log LR)

with alpha fitted here rather than guessed, and the customer-report prior fitted alongside it,
because "the customer denied it" was carrying more weight than the outcomes justify.

The cases are split in half: alpha is chosen on the dev half and every number worth quoting comes
from the held-out half, which the fit never saw. Writes data/processed/aggregation_fit.json.
"""

import argparse
import json
import logging
import math
import random

from redthread import paths

log = logging.getLogger("fit_aggregation")
FLOOR = 0.03
FRAUD_AT, LEGIT_AT = 0.85, 0.15

# What each outcome costs the bank, as the policy actually treats it. An uncertain verdict is not a
# wrong answer: policy escalates it to an analyst and asks the customer, so the case still gets
# handled. It is charged for the work it creates, and more when the truth was fraud, because a
# hesitated fraud is caught later and more expensively. A confident flip is charged in full: a
# blocked legitimate customer and a missed fraud are both real damage.
COST = {
    (True, "fraud"): 0.0,
    (True, "uncertain"): 0.3,
    (True, "legitimate"): 1.0,
    (False, "legitimate"): 0.0,
    (False, "uncertain"): 0.2,
    (False, "fraud"): 1.0,
}
OUT = paths.PROCESSED / "aggregation_fit.json"


def logit(p: float) -> float:
    return math.log(p / (1 - p))


def posterior(row: dict, alpha: float, prior_cr: float | None) -> float:
    """Recompute this case's probability under a tempering factor and an optional new prior."""
    belief = row["belief"]
    prior = belief["prior"]
    if prior_cr is not None and row.get("trigger_type") == "customer_report":
        prior = prior_cr
    total = sum(math.log(i["lr"]) for i in belief["ledger"] if i["counted"] and i["lr"] > 0)
    odds = math.exp(logit(prior) + alpha * total)
    return min(max(odds / (1 + odds), FLOOR), 1 - FLOOR)


def verdict(p: float) -> str:
    return "fraud" if p >= FRAUD_AT else "legitimate" if p <= LEGIT_AT else "uncertain"


def score(rows: list[dict], alpha: float, prior_cr: float | None) -> dict:
    """Brier, accuracy, and the split that shows whether the trigger is doing the work."""
    out: dict = {"n": len(rows)}
    briers, correct, costs, by_trigger = [], [], [], {}
    cleared_ok = cleared_n = fraud_ok = fraud_n = 0
    uncertain = 0
    for r in rows:
        fraud = r["truth_outcome"] == "confirmed_fraud"
        p = posterior(r, alpha, prior_cr)
        v = verdict(p)
        briers.append((p - float(fraud)) ** 2)
        # Same rule the backtest uses: only a 'fraud' verdict counts as calling it fraud.
        ok = (v == "fraud") == fraud
        correct.append(ok)
        uncertain += v == "uncertain"
        costs.append(COST[(fraud, v)])
        if fraud:
            fraud_n += 1
            fraud_ok += ok
        else:
            cleared_n += 1
            cleared_ok += ok
        by_trigger.setdefault(r.get("trigger_type", "?"), []).append(ok)
    out |= {
        "cost": round(sum(costs) / len(costs), 4),
        "brier": round(sum(briers) / len(briers), 4),
        "accuracy": round(sum(correct) / len(correct), 3),
        "fraud_recall": round(fraud_ok / fraud_n, 3) if fraud_n else None,
        "cleared_accuracy": round(cleared_ok / cleared_n, 3) if cleared_n else None,
        "uncertain": uncertain,
        "accuracy_by_trigger": {k: round(sum(v) / len(v), 3) for k, v in sorted(by_trigger.items())},
    }
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--backtest", default="runs/backtest_60.json")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--recall-giveback", type=float, default=0.10,
                        help="how much fraud recall may be traded away, in points, against the "
                             "untempered pipeline on the dev half")
    args = parser.parse_args()

    data = json.loads((paths.ROOT / args.backtest).read_text(encoding="utf-8"))
    rows = [r for r in data["cases"] if r.get("belief")]
    log.info("%d cases with a ledger", len(rows))

    rng = random.Random(args.seed)
    shuffled = rows[:]
    rng.shuffle(shuffled)
    half = len(shuffled) // 2
    dev, held = shuffled[:half], shuffled[half:]
    log.info("dev %d, held-out %d", len(dev), len(held))

    base = score(held, 1.0, None)
    log.info("\nbefore (held-out, alpha=1, prior unchanged): %s", json.dumps(base))

    dev_base = score(dev, 1.0, None)
    floor = dev_base["fraud_recall"] - args.recall_giveback
    log.info("dev before: %s", json.dumps(dev_base))
    log.info("keeping dev fraud recall at or above %.3f", floor)

    grid = []
    best = None
    for a20 in range(1, 21):
        alpha = a20 / 20
        for pc100 in list(range(25, 71, 5)) + [None]:
            prior_cr = None if pc100 is None else pc100 / 100
            s = score(dev, alpha, prior_cr)
            grid.append({"alpha": alpha, "prior_customer_report": prior_cr, **s})
            if s["fraud_recall"] < floor:
                continue
            if best is None or s["cost"] < best[0]["cost"]:
                best = (s, alpha, prior_cr)
    if best is None:
        raise SystemExit("no setting kept enough fraud recall; loosen --recall-giveback")
    dev_score, alpha, prior_cr = best
    log.info("\nfitted on dev: alpha=%.2f prior(customer_report)=%s -> %s",
             alpha, prior_cr, json.dumps(dev_score))

    log.info("\ntrade-off at the fitted prior (dev):")
    log.info("  alpha  cost   brier  acc    fraud  cleared  uncertain")
    for g in grid:
        if g["prior_customer_report"] == prior_cr and round(g["alpha"] * 20) % 2 == 0:
            log.info("  %.2f   %.3f  %.3f  %.3f  %.3f  %.3f    %d", g["alpha"], g["cost"],
                     g["brier"], g["accuracy"], g["fraud_recall"], g["cleared_accuracy"],
                     g["uncertain"])

    after = score(held, alpha, prior_cr)
    log.info("\nafter  (held-out): %s", json.dumps(after))
    log.info("\nheld-out: cost %.3f -> %.3f | Brier %.4f -> %.4f | accuracy %.3f -> %.3f | "
             "fraud %.3f -> %.3f | cleared %.3f -> %.3f",
             base["cost"], after["cost"], base["brier"], after["brier"],
             base["accuracy"], after["accuracy"], base["fraud_recall"], after["fraud_recall"],
             base["cleared_accuracy"], after["cleared_accuracy"])

    OUT.write_text(json.dumps({
        "alpha": alpha, "prior_customer_report": prior_cr, "seed": args.seed,
        "n_dev": len(dev), "n_held_out": len(held),
        "held_out_before": base, "held_out_after": after, "dev_after": dev_score,
        "dev_before": dev_base, "recall_giveback": args.recall_giveback, "grid": grid,
    }, indent=2), encoding="utf-8")
    log.info("\nwrote %s", OUT)


if __name__ == "__main__":
    main()
