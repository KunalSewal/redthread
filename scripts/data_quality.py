"""Data-quality report (challenge 11): the gaps that matter, and which investigations they taint.

    python scripts/data_quality.py

Each problem is measured on the data, lists affected record IDs (a sample, with the full count), and
names the final-round investigations whose evidence rests on an affected record. A taint does not
mean an answer is wrong; it means part of its evidence could not be what it appears to be, and an
analyst should know which part. Output: data/processed/data_quality.json.
"""

import json
import logging
from datetime import datetime

import pandas as pd

from redthread import paths
from redthread.data import sources

log = logging.getLogger("data_quality")
OUT = paths.PROCESSED / "data_quality.json"
SAMPLE = 12


def _ids(s: pd.Series) -> list[str]:
    return [str(x) for x in s.head(SAMPLE)]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    t = sources.processed_transactions(["card_id", "holder_id", "ts", "amount", "channel", "region", "device_id",
                                        "dist1", "D1", "risk_score"])
    t["ts"] = pd.to_datetime(t["ts"])
    t["month"] = sources.month_index(t["ts"])
    pack = pd.read_csv(sources.case_pack_csv(), dtype={"flagged_txn_id": str})
    flagged = pack.merge(t, left_on="flagged_txn_id", right_on="tx_id", how="left", suffixes=("", "_txn"))
    jan = t[t["month"] == 13]
    problems = []

    def add(name, what, affected: pd.Series, n: int, taints: list[str], why: str, **extra):
        problems.append({"problem": name, "what": what, "affected_count": int(n), "affected_sample": _ids(affected),
                         "taints": taints, "why_it_taints": why, **extra})

    # 1. No identity record: no device, no proxy flag, no match flags.
    no_id = t[t["device_id"].isna()]
    add("no identity record", "transactions with no identity row, so no device, proxy or match evidence",
        no_id["tx_id"], len(no_id),
        flagged[flagged["device_id"].isna()]["case_id"].tolist(),
        "the flagged transaction has no device: device newness, proxies and device rings cannot be checked",
        share=round(len(no_id) / len(t), 3), share_january=round(jan["device_id"].isna().mean(), 3))

    # 2. Empty billing region.
    no_region = t[t["region"].isna()]
    add("empty billing region", "transactions with no billing region (mostly online)",
        no_region["tx_id"], len(no_region),
        flagged[flagged["region"].isna()]["case_id"].tolist(),
        "out-of-region use cannot be judged for the flagged transaction", share=round(len(no_region) / len(t), 3))

    # 3. Placeholder distance.
    placeholder = t[t["dist1"] == -1]
    add("placeholder distance", "dist1 = -1 stands for 'unknown', not a distance", placeholder["tx_id"],
        len(placeholder), flagged[flagged["dist1"] == -1]["case_id"].tolist(),
        "distance from the billing address is unknown for the flagged transaction",
        share=round(len(placeholder) / len(t), 3))

    # 4. Holder linkage breaks in January: D1 no longer anchors a holder to their earlier history.
    seen_before = set(t[t["month"] <= 12]["holder_id"].dropna())
    dec = t[t["month"] == 12]
    seen_before_dec = set(t[t["month"] <= 11]["holder_id"].dropna())
    jan_linked = jan["holder_id"].isin(seen_before).mean()
    dec_linked = dec["holder_id"].isin(seen_before_dec).mean()
    unlinked = jan[~jan["holder_id"].isin(seen_before)]
    add("holder linkage drift in January",
        f"{jan_linked:.0%} of January transactions resolve to a holder seen before January, against "
        f"{dec_linked:.0%} for December against November; D1 in the January file does not continue the "
        "earlier day counts, so 'normal for this person' has almost no history in January",
        unlinked["tx_id"], len(unlinked), pack["case_id"].tolist(),
        "every final-round alert is in January: a holder-level baseline is thin or empty, so behaviour "
        "is judged at card level (an issuer bucket) or from the card's own run (redthread.schemes)",
        january_linked=round(float(jan_linked), 3), december_linked=round(float(dec_linked), 3))

    # 5. Thin card history before the alert.
    thin = []
    for r in flagged.itertuples():
        if pd.isna(r.card_id_txn):
            continue
        before = t[(t["card_id"] == r.card_id_txn) & (t["ts"] < pd.Timestamp(r.opened_at))
                   & (t["ts"] >= pd.Timestamp(r.opened_at) - pd.Timedelta(days=90))]
        if len(before) < 10:
            thin.append((r.case_id, r.card_id_txn, len(before)))
    add("too little card history", "cards with fewer than 10 transactions in the 90 days before the alert",
        pd.Series([c for _, c, _ in thin]), len(thin), [c for c, _, _ in thin],
        "what is 'new' for the card rests on very few transactions", detail=[
            {"case": c, "card": card, "txns_90d": n} for c, card, n in thin])

    # 6. The alert's labels disagree with its own transaction.
    mismatched = flagged[flagged["card_id"] != flagged["card_id_txn"]]
    add("alert names a different card from its transaction", "pack card_id differs from the flagged "
        "transaction's card", mismatched["flagged_txn_id"], len(mismatched), mismatched["case_id"].tolist(),
        "investigating the label would read the wrong card's history; the agent uses the transaction's card",
        detail=mismatched[["case_id", "card_id", "card_id_txn", "flagged_txn_id"]].to_dict("records"))
    channel_claims = flagged[flagged["trigger_text"].str.contains(r"\bonline\b", case=False, na=False)
                             & (flagged["channel"] == "in_person")]
    add("alert text contradicts its transaction", "the trigger text calls the transaction online, the record "
        "says in person", channel_claims["flagged_txn_id"], len(channel_claims), channel_claims["case_id"].tolist(),
        "free text about the transaction is not evidence of it; the record is used")
    gap = (flagged["risk_score"] - flagged["risk_score_txn"]).abs()
    score_gap = flagged[flagged["risk_score"].notna() & (gap > 0.01)]
    add("alert score differs from the transaction's", "pack risk_score differs from the transaction's own risk_score",
        score_gap["flagged_txn_id"], len(score_gap), score_gap["case_id"].tolist(),
        "the score quoted in the alert is not the one on record",
        detail=score_gap[["case_id", "risk_score", "risk_score_txn"]].to_dict("records"))

    out = {"made_at": datetime.now().isoformat(timespec="seconds"),
           "data": [p.name for p in sources.transaction_files()] + [sources.case_pack_csv().name],
           "transactions": len(t), "january_transactions": len(jan), "problems": problems,
           "investigations_tainted": sorted({c for p in problems for c in p["taints"]
                                             if p["problem"] != "holder linkage drift in January"})}
    OUT.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    for p in problems:
        log.info("%-48s %8d affected | taints %s", p["problem"], p["affected_count"], ", ".join(p["taints"])[:90])
    log.info("wrote %s", OUT)


if __name__ == "__main__":
    main()
