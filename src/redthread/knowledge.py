"""Fraud pattern definitions, verbatim from data/README.md ("The five known fraud patterns")."""

PATTERNS: dict[str, str] = {
    "card_testing": (
        "A stolen card number is checked before use: three or more tiny online authorizations, often "
        "under $5, then a larger purchase. Confirmed by the sequence itself. Policy R5."
    ),
    "card_not_present_fraud": (
        "The number is used online without the card. Amounts and products that don't fit the "
        "cardholder's history, often in a burst of two to four within 48 hours. On its own, one unusual "
        "online purchase is ambiguous: verify. Policy R1 to R4."
    ),
    "card_not_present_new_device": (
        "Same as card-not-present fraud, with the identity record marking the device as New for this "
        "account, sometimes behind a proxy. Stronger than pattern 2, still not proof: people buy new phones."
    ),
    "out_of_region_use": (
        "Card-present purchases in a billing region the cardholder has no history in, while their normal "
        "activity continues at home. Several days of purchases in one new region is a trip, not a clone. "
        "Policy R2, R3."
    ),
    "account_takeover": (
        "Mixed-channel activity inconsistent with the cardholder, often with device and match-flag "
        "anomalies, pointing to stolen credentials rather than a stolen number."
    ),
    "undocumented": (
        "Confirmed abuse that fits none of the five known patterns. Describe it in your own words. Policy R9."
    ),
    "none": "No fraud: the alert was a false alarm.",
}
