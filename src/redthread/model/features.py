"""Feature frame for the transaction fraud model.

Uses every original Vesta column (V, C, D, M, id_*) plus a few engineered features. The key one is
the holder key: ``customer_id`` is really an issuer bucket shared by many people, and
``card + billing region + (day - D1)`` separates the individual account holders inside it
(D1 counts days since the card's first use, so ``day - D1`` is constant for one holder).
"""

import numpy as np
import pandas as pd

from redthread import paths
from redthread.data.entities import SECONDS_PER_DAY, derive_card_ids, holder_ids

CATEGORICAL = [
    "ProductCD", "card4", "card6", "P_emaildomain", "R_emaildomain", *[f"M{i}" for i in range(1, 10)],
    *[f"id_{i}" for i in range(12, 39)], "DeviceType", "DeviceInfo",
]
DROP = ["TransactionID", "TransactionDT", "customer_id", "ts", "channel", "card_id"]


def load_raw() -> pd.DataFrame:
    """Transactions joined to identity, numeric columns as float32 to fit in memory."""
    tx = pd.read_csv(paths.TRANSACTIONS_CSV, engine="pyarrow")
    ident = pd.read_csv(paths.IDENTITY_CSV, engine="pyarrow")
    tx = tx.merge(ident, on="TransactionID", how="left")
    numeric = tx.select_dtypes("number").columns.difference(["TransactionID", "TransactionDT"])
    tx[numeric] = tx[numeric].astype("float32")
    return tx


def build_features(tx: pd.DataFrame) -> pd.DataFrame:
    """Return the model matrix, indexed like ``tx``. Label-free: safe to compute over all months."""
    x = tx.copy()
    x["card_id"] = derive_card_ids(x["customer_id"], x["card6"])
    day = np.floor(x["TransactionDT"] / SECONDS_PER_DAY)
    ts = pd.to_datetime(x["ts"])
    x["hour"] = ts.dt.hour.astype("float32")
    x["weekday"] = ts.dt.weekday.astype("float32")
    x["cents"] = (x["TransactionAmt"] - np.floor(x["TransactionAmt"])).astype("float32")

    # Normalized time deltas: constant per holder, so they identify the holder rather than the day.
    for col in ["D1", "D2", "D3", "D4", "D10", "D11", "D15"]:
        x[f"{col}n"] = (day - x[col]).astype("float32")

    x["holder"] = holder_ids(x["card_id"], x["addr1"], x["TransactionDT"], x["D1"])
    x["holder_email"] = x["holder"] + "|" + x["P_emaildomain"].astype(str)
    for key in ["holder", "holder_email", "card_id"]:
        grp = x.groupby(key)["TransactionAmt"]
        x[f"{key}_n"] = grp.transform("size").astype("float32")
        x[f"{key}_amt_mean"] = grp.transform("mean").astype("float32")
        x[f"{key}_amt_std"] = grp.transform("std").astype("float32")
        x[f"{key}_amt_ratio"] = (x["TransactionAmt"] / x[f"{key}_amt_mean"]).astype("float32")
    for col in ["P_emaildomain", "addr1", "DeviceInfo", "id_31", "id_33", "C13", "V258"]:
        x[f"holder_nuniq_{col}"] = x.groupby("holder")[col].transform("nunique").astype("float32")
    for col in ["card_id", "addr1", "P_emaildomain", "DeviceInfo", "id_31", "holder"]:
        x[f"freq_{col}"] = x[col].map(x[col].value_counts(dropna=False)).astype("float32")

    for col in CATEGORICAL + ["holder", "holder_email"]:
        x[col] = x[col].astype("category").cat.codes.astype("int32")
    return x.drop(columns=DROP)


def closed_case_labels(tx_ids: pd.Series) -> pd.Series:
    """1 if the transaction is in a confirmed-fraud closed case, else 0."""
    closed = pd.read_csv(paths.CLOSED_CASES_CSV, usecols=["outcome", "txn_ids"])
    fraud = closed[closed["outcome"] == "confirmed_fraud"]["txn_ids"].astype(str).str.split("|").explode()
    return tx_ids.isin(set(fraud.astype(int))).astype("int8")
