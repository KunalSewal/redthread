"""Turn the raw dataset into vertex/edge files for the TigerGraph loading jobs.

Reads data/*.csv, writes data/processed/*.csv (git-ignored). Idempotent: rerun after any change.

    python scripts/prepare_data.py

The 339 V-features are not loaded into the graph: they are unnamed model features that no query
traverses on. Named signal columns (C, D, M, identity flags) are kept as typed attributes.
"""

import logging
import time

import pandas as pd

from redthread import paths
from redthread.data.entities import derive_card_ids, device_profile_strings, holder_ids, region_code
from redthread.knowledge import PATTERNS

log = logging.getLogger("prepare_data")

TXN_CHUNK_ROWS = 100_000  # keeps each upload file well under the REST payload limit
# TigerGraph loads an empty numeric field as 0, which would read as a real value (a model score of 0,
# D1 = 0 "first use today"). Graph numeric columns use -1 for "missing" instead.
MISSING_NUMERIC = -1
GRAPH_NUMERIC = ["model_score", "dist1", "C1", "C13", "C14", "D1", "D15"]

C_COLS = [f"C{i}" for i in range(1, 15)]
D_COLS = [f"D{i}" for i in range(1, 16)]
M_COLS = [f"M{i}" for i in range(1, 10)]
TXN_SOURCE_COLS = [
    "TransactionID", "TransactionDT", "TransactionAmt", "ProductCD", "card4", "card6",
    "addr1", "addr2", "dist1", "dist2", "P_emaildomain", "R_emaildomain",
    "customer_id", "ts", "channel", "risk_score", *C_COLS, *D_COLS, *M_COLS,
]
IDENTITY_COLS = ["TransactionID", "id_15", "id_23", "id_34", "DeviceType", "DeviceInfo", "id_30", "id_31", "id_33"]


def build_devices(identity: pd.DataFrame, txn_ts: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Assign stable device IDs (D000001...) in order of first use, and map transactions to them."""
    identity = identity.copy()
    identity["profile"] = device_profile_strings(identity)
    identity = identity[identity["profile"].notna()]
    identity["ts"] = identity["TransactionID"].map(txn_ts)
    first_seen = identity.sort_values(["ts", "TransactionID"]).drop_duplicates("profile")
    first_seen = first_seen.reset_index(drop=True)
    first_seen["device_id"] = [f"D{i:06d}" for i in range(1, len(first_seen) + 1)]
    devices = first_seen.rename(columns={
        "DeviceInfo": "device_info", "id_30": "os", "id_31": "browser", "id_33": "screen",
        "DeviceType": "device_type", "ts": "first_seen",
    })[["device_id", "profile", "device_info", "os", "browser", "screen", "device_type", "first_seen"]]
    tx_device = identity.merge(devices[["device_id", "profile"]], on="profile")[["TransactionID", "device_id"]]
    return devices, tx_device.rename(columns={"TransactionID": "tx_id"})


def build_transactions(tx: pd.DataFrame, identity: pd.DataFrame, tx_device: pd.DataFrame) -> pd.DataFrame:
    ident = identity.rename(columns={
        "id_15": "device_status", "id_23": "proxy", "id_34": "match_status", "DeviceType": "device_type",
    })[["TransactionID", "device_status", "proxy", "match_status", "device_type"]]
    out = tx.merge(ident, on="TransactionID", how="left", validate="one_to_one")
    out = out.merge(tx_device.rename(columns={"tx_id": "TransactionID"}), on="TransactionID", how="left")
    out["region"] = region_code(out["addr1"])
    out["country"] = region_code(out["addr2"])
    out["holder_id"] = holder_ids(out["card_id"], out["addr1"], out["TransactionDT"], out["D1"])
    out = out.rename(columns={
        "TransactionID": "tx_id", "TransactionDT": "dt_seconds", "TransactionAmt": "amount",
        "ProductCD": "product_cd", "P_emaildomain": "p_email", "R_emaildomain": "r_email",
    })
    cols = [  # model_score is appended by attach_model_scores
        "tx_id", "card_id", "customer_id", "holder_id", "ts", "dt_seconds", "amount", "product_cd", "channel",
        "risk_score", "region", "country", "dist1", "dist2", "p_email", "r_email", "card4", "card6",
        "device_id", "device_status", "proxy", "match_status", "device_type", *C_COLS, *D_COLS, *M_COLS,
    ]
    return out[cols].sort_values("tx_id")


def build_holders(txns: pd.DataFrame) -> pd.DataFrame:
    parts = txns["holder_id"].str.split("|", expand=True)
    frame = txns.assign(region_part=parts[1], anchor_day=parts[2])
    return (
        frame.groupby("holder_id")
        .agg(card_id=("card_id", "first"), region=("region_part", "first"), anchor_day=("anchor_day", "first"),
             n_txns=("tx_id", "size"), first_ts=("ts", "min"), last_ts=("ts", "max"),
             amount_mean=("amount", "mean"))
        .reset_index()
        .round({"amount_mean": 2})
    )


def build_card_device(txns: pd.DataFrame) -> pd.DataFrame:
    """One edge per (card, device) with usage counts: the projection ring detection runs on."""
    used = txns.dropna(subset=["device_id"])
    return (
        used.groupby(["card_id", "device_id"])
        .agg(n_txns=("tx_id", "size"), first_ts=("ts", "min"), last_ts=("ts", "max"))
        .reset_index()
    )


def attach_model_scores(txns: pd.DataFrame) -> pd.DataFrame:
    scores_path = paths.PROCESSED / "txn_scores.csv"
    if not scores_path.exists():
        log.warning("no txn_scores.csv; run scripts/train_model.py first. model_score left empty")
        return txns.assign(model_score=pd.NA)
    scores = pd.read_csv(scores_path)
    return txns.merge(scores, on="tx_id", how="left", validate="one_to_one")


def build_next_edges(txns: pd.DataFrame) -> pd.DataFrame:
    """Chain each card's transactions in time order, with the gap in seconds."""
    ordered = txns[["tx_id", "card_id", "ts"]].sort_values(["card_id", "ts", "tx_id"])
    ts = pd.to_datetime(ordered["ts"])
    same_card = ordered["card_id"].eq(ordered["card_id"].shift(-1))
    edges = pd.DataFrame({
        "from_tx": ordered["tx_id"],
        "to_tx": ordered["tx_id"].shift(-1),
        "gap_s": (ts.shift(-1) - ts).dt.total_seconds(),
    })[same_card]
    return edges.astype({"to_tx": "int64", "gap_s": "int64"})


def build_closed_cases(closed: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cases = closed.drop(columns=["txn_ids", "connected_card_ids"]).copy()
    cases["first_fraud_txn_id"] = cases["first_fraud_txn_id"].map(lambda v: "" if pd.isna(v) else str(int(v)))
    involves = closed[["case_id", "txn_ids"]].assign(tx_id=closed["txn_ids"].astype(str).str.split("|"))
    involves = involves.explode("tx_id")[["case_id", "tx_id"]]
    connected = closed[["case_id", "connected_card_ids"]].dropna()
    connected = connected.assign(card_id=connected["connected_card_ids"].str.split("|")).explode("card_id")
    return cases, involves, connected[["case_id", "card_id"]]


def write(frame: pd.DataFrame, name: str) -> None:
    path = paths.PROCESSED / name
    frame.to_csv(path, index=False)
    log.info("wrote %-28s %9d rows", name, len(frame))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    start = time.time()
    paths.PROCESSED.mkdir(parents=True, exist_ok=True)

    tx = pd.read_csv(paths.TRANSACTIONS_CSV, usecols=TXN_SOURCE_COLS, low_memory=False)
    identity = pd.read_csv(paths.IDENTITY_CSV, usecols=IDENTITY_COLS, low_memory=False)
    closed = pd.read_csv(paths.CLOSED_CASES_CSV)
    log.info("read %d transactions, %d identity rows, %d closed cases", len(tx), len(identity), len(closed))

    tx["card_id"] = derive_card_ids(tx["customer_id"], tx["card6"])
    devices, tx_device = build_devices(identity, tx.set_index("TransactionID")["ts"])
    txns = attach_model_scores(build_transactions(tx, identity, tx_device))
    card_device = build_card_device(txns)
    devices["n_cards"] = devices["device_id"].map(card_device.groupby("device_id").size()).fillna(0).astype(int)

    cards = (
        txns.groupby("card_id")
        .agg(customer_id=("customer_id", "first"), card4=("card4", "first"), card6=("card6", "first"))
        .reset_index()
    )
    customers = cards.groupby("customer_id").size().rename("n_cards").reset_index()

    graph_txns = txns.copy()
    graph_txns[GRAPH_NUMERIC] = graph_txns[GRAPH_NUMERIC].fillna(MISSING_NUMERIC)
    for i, start_row in enumerate(range(0, len(graph_txns), TXN_CHUNK_ROWS)):
        write(graph_txns.iloc[start_row:start_row + TXN_CHUNK_ROWS], f"transactions_{i:02d}.csv")
    write(pd.DataFrame(PATTERNS.items(), columns=["name", "description"]), "patterns.csv")
    write(customers, "customers.csv")
    write(cards, "cards.csv")
    write(devices, "devices.csv")
    write(build_holders(txns), "holders.csv")
    write(card_device, "card_device.csv")
    write(build_next_edges(txns), "next_edges.csv")

    cases, involves, connected = build_closed_cases(closed)
    write(cases, "closed_cases.csv")
    write(involves, "closed_case_involves.csv")
    write(connected, "closed_case_connected.csv")
    log.info("done in %.0fs", time.time() - start)


if __name__ == "__main__":
    main()
