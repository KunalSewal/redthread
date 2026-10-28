import pandas as pd
import pytest

from redthread import paths
from redthread.data import sources
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
@pytest.mark.skipif(not sources.transaction_files(), reason="dataset not present")
def test_card_ids_reproduce_every_labeled_card():
    """Every card ID the bank wrote down must come out of our derivation, with January loaded too.

    Card numbers are ranks over each customer's card types across all loaded data, so a new month
    could renumber existing cards; this would catch it on both rounds' cases and case packs."""
    tx = sources.read_transactions(usecols=["TransactionID", "customer_id", "card6"])
    tx["card_id"] = derive_card_ids(tx["customer_id"], tx["card6"])
    derived = tx.set_index("TransactionID")["card_id"]

    closed = pd.read_csv(sources.closed_cases_csv(), usecols=["card_id", "txn_ids"])
    closed = closed.assign(txn=closed["txn_ids"].astype(str).str.split("|")).explode("txn")
    packs = [paths.DATA / "case_pack.csv", paths.DATA_R2 / "cases" / "case_pack_final.csv"]
    pack = pd.concat([pd.read_csv(f, usecols=["card_id", "flagged_txn_id"]) for f in packs if f.exists()])
    labels = pd.concat([
        closed[["txn", "card_id"]].rename(columns={"txn": "tid"}),
        pack.rename(columns={"flagged_txn_id": "tid"}),
    ])
    # The appended HHG cases that were cleared list no transactions; older cleared cases always did.
    labels = labels[labels["tid"].astype(str).str.fullmatch(r"\d+")]
    labels["tid"] = labels["tid"].astype(int)

    assert len(labels) > 14_000
    mismatches = labels[derived.loc[labels["tid"]].to_numpy() != labels["card_id"].to_numpy()]
    # HHF-011's alert names C09241-K1, but the bank's 21 closed cases on the same debit card all say
    # C09241-K2, as does our derivation. The pack contradicts the bank's own records there; the agent
    # takes the card from the flagged transaction and notes the discrepancy. Anything else fails.
    known_pack_errors = {(3640919, "C09241-K1")}
    unexpected = mismatches[[(t, c) not in known_pack_errors
                             for t, c in zip(mismatches["tid"], mismatches["card_id"], strict=True)]]
    assert unexpected.empty, unexpected.head()
