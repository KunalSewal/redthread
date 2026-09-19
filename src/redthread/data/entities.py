"""Derivations for entities the dataset implies but does not store as columns.

Card IDs (``C01234-K1``) and device profiles appear in the closed cases and the answer format,
but ``transactions.csv`` has neither. These functions are the single definition of both;
the loader, the agent, and the ID validator all go through them.
"""

import pandas as pd

DEVICE_FIELDS = ("DeviceInfo", "id_30", "id_31", "id_33")  # device, OS, browser, screen
DEVICE_SEPARATOR = " | "
MISSING = "unknown"


def derive_card_ids(customer_id: pd.Series, card6: pd.Series) -> pd.Series:
    """Return ``<customer_id>-K<n>`` for each transaction.

    ``n`` is the 1-based rank of the transaction's ``card6`` value among the customer's distinct
    ``card6`` values, compared as plain strings with a null value sorting first. This reproduces
    every card ID in ``closed_cases_history.csv`` and ``case_pack.csv`` (see
    ``context/data-dictionary.md``). Nulls are mapped to ``""`` explicitly so the result does not
    depend on how a pandas version stringifies missing values.
    """
    key = card6.astype(object).where(card6.notna(), "").astype(str)
    frame = pd.DataFrame({"customer_id": customer_id.astype(str), "key": key})
    distinct = frame.drop_duplicates().sort_values(["customer_id", "key"], kind="stable")
    distinct["rank"] = distinct.groupby("customer_id").cumcount() + 1
    ranked = frame.merge(distinct, on=["customer_id", "key"], how="left", validate="many_to_one")
    ids = ranked["customer_id"] + "-K" + ranked["rank"].astype(str)
    ids.index = customer_id.index
    return ids


def device_profile_strings(identity: pd.DataFrame) -> pd.Series:
    """Return ``DeviceInfo | OS | browser | screen`` per identity row, or null when all four are missing.

    Matches the profile format in the README's answer example.
    """
    parts = identity[list(DEVICE_FIELDS)].astype(object)
    all_missing = parts.isna().all(axis=1)
    text = parts.where(parts.notna(), MISSING).astype(str).agg(DEVICE_SEPARATOR.join, axis=1)
    return text.where(~all_missing)


def region_code(addr1: pd.Series) -> pd.Series:
    """Billing region codes as strings (``264.0`` becomes ``"264"``); null stays null."""
    return addr1.map(lambda v: None if pd.isna(v) else str(int(v)))
