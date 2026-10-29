"""Containment planner: the fewest blocks that stop the most of a ring's exposure (challenge 7).

A ring's loss is a set of transactions on cards, some of them reached through something the cards
share: a device profile, a recipient email. Two kinds of action stop it:

- **block a card**: stops every ring transaction on that card, and acts against everyone else who
  uses the card. Cards here are issuer buckets shared by many unrelated people, so blocking one is
  rarely a one-person action.
- **block a shared element** (decline what comes from that device, or what pays that recipient):
  stops the ring's transactions through it on every card, and acts against the element's other,
  legitimate users.

The plan maximises the expected value of acting: each ring transaction counts at its amount times the
probability that its card is compromised (``Item.p_fraud``), and each customer an action touches costs
``penalty_usd`` times the probability that the customer is legitimate (``Action.p_legit``). A card
whose fraud is established has p_legit 0; a card that only shows the ring's behaviour is a coin the
plan has to pay for. With up to
EXACT_LIMIT candidate actions every combination is tried, so the plan is optimal; above that a
greedy pass is used (marginal gain, stopping when no action pays for the people it touches). Ties go
to the smaller plan. Every plan states the amounts it cuts and leaves, and names who it touches.
"""

from dataclasses import dataclass, field
from itertools import combinations

EXACT_LIMIT = 16
DEFAULT_PENALTY_USD = 250.0  # what acting against one legitimate customer is counted as costing


@dataclass(frozen=True)
class Item:
    """One ring transaction: its card, its amount, and the shared elements it came through."""

    tx_id: str
    card_id: str
    amount: float
    via: frozenset[str] = frozenset()
    p_fraud: float = 1.0  # how likely the card this ran on is compromised


@dataclass(frozen=True)
class Action:
    kind: str  # "card" or the element kind ("device", "recipient")
    target: str
    touches: frozenset[str]  # customers this action acts against who may be legitimate
    p_legit: float = 1.0  # how likely each of them is legitimate

    def covers(self, item: Item) -> bool:
        return item.card_id == self.target if self.kind == "card" else self.target in item.via


@dataclass
class Plan:
    actions: list[Action]
    exposure_total: float
    exposure_cut: float
    customers_touched: list[str]
    penalty_usd: float
    method: str
    cut_by_action: dict[str, float] = field(default_factory=dict)
    expected_cut: float = 0.0
    expected_harm: float = 0.0  # expected legitimate customers acted against

    @property
    def exposure_left(self) -> float:
        return round(self.exposure_total - self.exposure_cut, 2)

    @property
    def net(self) -> float:
        return round(self.expected_cut - self.penalty_usd * self.expected_harm, 2)

    def as_dict(self) -> dict:
        return {"actions": [{"kind": a.kind, "target": a.target, "cuts_usd": self.cut_by_action.get(_key(a), 0.0),
                             "touches": sorted(a.touches)} for a in self.actions],
                "exposure_total_usd": round(self.exposure_total, 2), "exposure_cut_usd": round(self.exposure_cut, 2),
                "exposure_left_usd": self.exposure_left, "customers_touched": self.customers_touched,
                "expected_cut_usd": round(self.expected_cut, 2),
                "expected_legitimate_customers_touched": round(self.expected_harm, 2),
                "penalty_usd_per_customer": self.penalty_usd, "net_expected_usd": self.net, "method": self.method}


def _key(a: Action) -> str:
    return f"{a.kind}:{a.target}"


def _score(chosen: tuple[Action, ...], items: list[Item], penalty: float):
    """(net expected value, amount cut, customers touched, expected cut, expected harm)."""
    stopped = [i for i in items if any(a.covers(i) for a in chosen)]
    cut, expected_cut = sum(i.amount for i in stopped), sum(i.amount * i.p_fraud for i in stopped)
    p_touch: dict[str, float] = {}
    for a in chosen:
        for c in a.touches:
            p_touch[c] = max(p_touch.get(c, 0.0), a.p_legit)
    harm = sum(p_touch.values())
    return expected_cut - penalty * harm, cut, set(p_touch), expected_cut, harm


def plan(items: list[Item], candidates: list[Action], penalty_usd: float = DEFAULT_PENALTY_USD) -> Plan:
    useful = [a for a in candidates if any(a.covers(i) for i in items)]
    total = round(sum(i.amount for i in items), 2)
    best: tuple[Action, ...] = ()
    best_key = (0.0, 0, 0.0)  # (net, -size, cut): the empty plan is the floor
    if len(useful) <= EXACT_LIMIT:
        method = f"exact over {len(useful)} candidate actions"
        for size in range(1, len(useful) + 1):
            for combo in combinations(useful, size):
                net, cut, *_ = _score(combo, items, penalty_usd)
                key = (round(net, 6), -size, round(cut, 6))
                if key > best_key:
                    best, best_key = combo, key
    else:
        method = f"greedy over {len(useful)} candidate actions"
        chosen: list[Action] = []
        while True:
            current = _score(tuple(chosen), items, penalty_usd)[0]
            gains = [(_score((*chosen, a), items, penalty_usd)[0] - current, a) for a in useful if a not in chosen]
            gains = [g for g in gains if g[0] > 1e-9]
            if not gains:
                break
            chosen.append(max(gains, key=lambda g: g[0])[1])
        best = tuple(chosen)
    _, cut, touched, expected_cut, harm = _score(best, items, penalty_usd)
    cut_by: dict[str, float] = {}
    covered: set[str] = set()
    for a in best:  # attribute each transaction to the first action in the plan that stops it
        amt = sum(i.amount for i in items if a.covers(i) and i.tx_id not in covered)
        covered |= {i.tx_id for i in items if a.covers(i)}
        cut_by[_key(a)] = round(amt, 2)
    return Plan(actions=list(best), exposure_total=total, exposure_cut=round(cut, 2),
                customers_touched=sorted(touched), penalty_usd=penalty_usd, method=method, cut_by_action=cut_by,
                expected_cut=expected_cut, expected_harm=harm)


def block_everything(items: list[Item], candidates: list[Action], penalty_usd: float = DEFAULT_PENALTY_USD) -> Plan:
    """The comparison: block every card in the ring, which is what a card-by-card response does."""
    cards = [a for a in candidates if a.kind == "card" and any(a.covers(i) for i in items)]
    _, cut, touched, expected_cut, harm = _score(tuple(cards), items, penalty_usd)
    return Plan(actions=cards, exposure_total=round(sum(i.amount for i in items), 2), exposure_cut=round(cut, 2),
                customers_touched=sorted(touched), penalty_usd=penalty_usd, method="block every ring card",
                expected_cut=expected_cut, expected_harm=harm)
