"""Activity a card has never made, and the same thing happening on other customers' cards at once.

The January schemes do not sit on a card instead of its ordinary activity; they sit beside it. A card
that buys groceries in person every week suddenly carries six online charges of $2 to $5 over three
weeks, or three $800 online purchases from a new phone behind an anonymous proxy. Two questions
follow, and both are answered from GSQL results here, deterministically:

1. **Is the flagged charge part of a run the card has never made?** ``new_kind_run`` returns the
   card's transactions in the 30 days up to the alert whose kind (product and channel) was under 5%
   of its activity in the 60 days before. On Round 1's 20 known outcomes every alert in such a run of
   two or more was confirmed fraud (3 of 3) and every single new-kind charge was cleared (3 of 3); on
   the bank's own closed cases the rule does not separate fraud from cleared alerts at all (3.4% and
   3.8%). It is moderate evidence (run_strength), and a run of one is not a finding.
2. **Are other customers doing the same thing at the same moment?** ``scheme_peers`` counts cards that
   newly show the run's signature in the alert's window, and in the same window one and two months
   earlier. Small online probes appeared on 20 cards in January against 3 to 7 a month before; large
   proxied charges from new devices on 5 against none. A count that jumps is repeated abuse across
   customers (R9's words), and the organisers' own answer for such a scheme (Round 1's HHG-006, four
   charges just under $500) lists the other cards running it as connected cards.

Nothing here reads a transaction after the alert.
"""

from dataclasses import dataclass

SMALL_AUTH_USD = 10.0  # the probe size R5 and the README describe ("often under $5")
MIN_BASELINE_TXNS = 3  # with less history than this, nothing is "new" to the card
BAND_LOW, BAND_HIGH = 0.8, 1.25  # a peer's amounts sit near the run's own


@dataclass(frozen=True)
class Signature:
    product: str
    channel: str
    amount_lo: float
    amount_hi: float
    need_new_device: bool
    need_proxy: bool
    probes: bool  # every charge in the run is a small authorisation
    min_txns: int

    def describe(self) -> str:
        what = (f"{self.min_txns}+ online authorisations under ${SMALL_AUTH_USD:.0f}" if self.probes else
                f"{self.min_txns}+ {self.channel} product-{self.product} charges of "
                f"${self.amount_lo:,.0f}-${self.amount_hi:,.0f}")
        extra = [x for x, on in (("from a device new to the account", self.need_new_device),
                                 ("behind a proxy", self.need_proxy)) if on]
        return " ".join([what, *extra]) + ", on a card that had not made such charges before"


def flagged_run(rows: list[dict], flagged_tx: str, baseline_txns: int) -> list[dict]:
    """The run the flagged charge belongs to: the new-kind rows of its own kind, oldest first.

    Empty when the flagged charge is not new to the card, when the card has too little history to say,
    or when the run is a single charge (on its own, one unusual purchase is ambiguous: the README).
    """
    if baseline_txns < MIN_BASELINE_TXNS:
        return []
    flagged = next((r for r in rows if r["tx_id"] == flagged_tx), None)
    if flagged is None:
        return []
    run = sorted((r for r in rows if r["product"] == flagged["product"] and r["channel"] == flagged["channel"]),
                 key=lambda r: r["ts"])
    return run if len(run) >= 2 else []


def signature(run: list[dict]) -> Signature | None:
    if not run:
        return None
    amounts = [abs(r["amount"]) for r in run]
    probes = max(amounts) < SMALL_AUTH_USD
    if probes:
        lo, hi = 0.0, SMALL_AUTH_USD
    else:
        lo, hi = round(min(amounts) * BAND_LOW, 2), round(max(amounts) * BAND_HIGH, 2)
    new_device = all(r.get("device_status") == "New" for r in run)
    proxy = all(bool(r.get("proxy")) for r in run)
    # How many matching charges make a card a peer depends on how rare the signature is. Two small
    # online charges on a card new to them are common (18 cards in December's window); two large ones
    # from a new device or behind a proxy appeared on no card before January.
    min_txns = 2 if new_device or proxy else min(3, len(run))
    return Signature(product=run[0]["product"], channel=run[0]["channel"], amount_lo=lo, amount_hi=hi,
                     need_new_device=new_device, need_proxy=proxy, probes=probes, min_txns=min_txns)


def run_strength(run: list[dict]) -> str | None:
    """A run of two or more charges the card never made is moderate evidence; one is nothing.

    Measured two ways (scripts/backtest_detectors.py, data/processed/detector_backtest.json). On the
    review queue this pack is drawn from (Round 1's 20), runs were on 3 of 10 frauds and 0 of 10
    cleared alerts: likelihood ratio (3+1)/(10+2) over (0+1)/(10+2) = 4, between moderate and strong.
    On the bank's own 5,585 closed cases, a population drawn differently, the rule fired on 3.4% of
    confirmed frauds and 3.8% of cleared alerts: no evidence at all. So a run is moderate, never strong,
    and what makes it a scheme is the same behaviour starting on other customers' cards (peer_strength).
    """
    return "moderate" if len(run) >= 2 else None


def peer_strength(now: int, earlier: list[int]) -> str | None:
    """How much it says that other customers started the same thing in the same window.

    ``now`` counts the other cards (the alert's own excluded); ``earlier`` the same window one and two
    months before. A count that is high and well above its own history is repeated abuse; a count at
    its usual level is just how people shop.
    """
    usual = max(1.0, sum(earlier) / len(earlier)) if earlier else 1.0
    lift = now / usual
    if now >= 4 and lift >= 3:
        return "strong"
    if now >= 2 and lift >= 2:
        return "moderate"
    return None


def fits_card_testing(run: list[dict]) -> bool:
    """Whether a run of probes is documented card testing (R5) or something the policy does not name.

    R5 and the README define card testing by its sequence: three or more tiny online authorisations
    within an hour, then a larger purchase. Probes spread over weeks with no purchase after them are
    a different scheme, one built to stay under per-hour velocity rules.
    """
    from redthread.patterns import card_testing_sequence

    rows = [{"channel": r["channel"], "ts": r["ts"], "amount": abs(r["amount"])} for r in run]
    return card_testing_sequence(rows)
