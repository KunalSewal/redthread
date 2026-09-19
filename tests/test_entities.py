import pandas as pd
import pytest

from redthread import paths
from redthread.data.entities import derive_card_ids, device_profile_strings, holder_ids, region_code


def test_card_ids_rank_card_types_alphabetically_with_null_first():
    customer = pd.Series(["C1", "C1", "C1", "C2", "C2", "C1"])
    card6 = pd.Series(["debit", "credit", None, "debit", "debit", "debit"])
    assert derive_card_ids(customer, card6).tolist() == [
        "C1-K3", "C1-K2", "C1-K1", "C2-K1", "C2-K1", "C1-K3",
    ]


def test_card_ids_preserve_index():
    customer = pd.Series(["C1", "C1"], index=[10, 20])
    card6 = pd.Series(["debit", "credit"], index=[10, 20])
    assert derive_card_ids(customer, card6).to_dict() == {10: "C1-K2", 20: "C1-K1"}


def test_device_profile_format_and_all_missing():
    identity = pd.DataFrame({
        "DeviceInfo": ["SAMSUNG SM-G892A Build/NRD90M", None],
        "id_30": ["Android 7.0", None],
        "id_31": ["samsung browser 6.2", None],
        "id_33": [None, None],
    })
    profiles = device_profile_strings(identity)
    assert profiles[0] == "SAMSUNG SM-G892A Build/NRD90M | Android 7.0 | samsung browser 6.2 | unknown"
    assert pd.isna(profiles[1])


def test_holder_ids_share_anchor_day():
    # Same card and region; day 100 with D1=10 and day 105 with D1=15 are the same holder.
    card = pd.Series(["C1-K1", "C1-K1", "C1-K1"])
    addr1 = pd.Series([264.0, 264.0, None])
    dt = pd.Series([100 * 86_400 + 5, 105 * 86_400 + 99, 7])
    d1 = pd.Series([10.0, 15.0, None])
    assert holder_ids(card, addr1, dt, d1).tolist() == ["C1-K1|264|90", "C1-K1|264|90", "C1-K1|NA|NA"]


def test_region_code():
    codes = region_code(pd.Series([264.0, None]))
    assert codes[0] == "264"
    assert pd.isna(codes[1])


@pytest.mark.data
@pytest.mark.skipif(not paths.TRANSACTIONS_CSV.exists(), reason="dataset not present")
def test_card_ids_reproduce_every_labeled_card():
    """Every card ID the bank wrote down must come out of our derivation."""
    tx = pd.read_csv(paths.TRANSACTIONS_CSV, usecols=["TransactionID", "customer_id", "card6"])
    tx["card_id"] = derive_card_ids(tx["customer_id"], tx["card6"])
    derived = tx.set_index("TransactionID")["card_id"]

    closed = pd.read_csv(paths.CLOSED_CASES_CSV, usecols=["card_id", "txn_ids"])
    closed = closed.assign(txn=closed["txn_ids"].astype(str).str.split("|")).explode("txn")
    pack = pd.read_csv(paths.CASE_PACK_CSV, usecols=["card_id", "flagged_txn_id"])
    labels = pd.concat([
        closed[["txn", "card_id"]].rename(columns={"txn": "tid"}),
        pack.rename(columns={"flagged_txn_id": "tid"}),
    ])
    labels["tid"] = labels["tid"].astype(int)

    assert len(labels) > 14_000
    mismatches = labels[derived.loc[labels["tid"]].to_numpy() != labels["card_id"].to_numpy()]
    assert mismatches.empty, mismatches.head()
