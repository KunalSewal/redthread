"""Containment planner: the fewest blocks that stop the most of a ring's exposure (challenge 7).

A ring's loss is a set of transactions on cards, some of them reached through something the cards
share: a device profile, a recipient email. Two kinds of action stop it:

- **block a card**: stops every ring transaction on that card, and acts against everyone else who
  uses the card. Cards here are issuer buckets shared by many unrelated people, so blocking one is
  rarely a one-person action.
- **block a shared element** (decline what comes from that device, or what pays that recipient):
  stops the ring's transactions through it on every card, and acts against the element's other,
  legitimate users.

The plan maximises ``exposure cut - penalty_usd x legitimate customers touched``. With up to
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


@dataclass(frozen=True)
class Action:
    kind: str  # "card" or the element kind ("device", "recipient")
    target: str
    touches: frozenset[str]  # legitimate customers this action acts against

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

    @property
    def exposure_left(self) -> float:
        return round(self.exposure_total - self.exposure_cut, 2)

    @property
    def net(self) -> float:
        return round(self.exposure_cut - self.penalty_usd * len(self.customers_touched), 2)

    def as_dict(self) -> dict:
        return {"actions": [{"kind": a.kind, "target": a.target, "cuts_usd": self.cut_by_action.get(_key(a), 0.0),
                             "touches": sorted(a.touches)} for a in self.actions],
                "exposure_total_usd": round(self.exposure_total, 2), "exposure_cut_usd": round(self.exposure_cut, 2),
                "exposure_left_usd": self.exposure_left, "customers_touched": self.customers_touched,
                "penalty_usd_per_customer": self.penalty_usd, "net_usd": self.net, "method": self.method}


def _key(a: Action) -> str:
    return f"{a.kind}:{a.target}"


def _score(chosen: tuple[Action, ...], items: list[Item], penalty: float) -> tuple[float, float, set[str]]:
    cut = sum(i.amount for i in items if any(a.covers(i) for a in chosen))
    touched = set().union(*(a.touches for a in chosen)) if chosen else set()
    return cut - penalty * len(touched), cut, touched


def plan(items: list[Item], candidates: list[Action], penalty_usd: float = DEFAULT_PENALTY_USD) -> Plan:
    useful = [a for a in candidates if any(a.covers(i) for i in items)]
    total = round(sum(i.amount for i in items), 2)
    best: tuple[Action, ...] = ()
    best_key = (0.0, 0, 0.0)  # (net, -size, cut): the empty plan is the floor
    if len(useful) <= EXACT_LIMIT:
        method = f"exact over {len(useful)} candidate actions"
        for size in range(1, len(useful) + 1):
            for combo in combinations(useful, size):
                net, cut, _ = _score(combo, items, penalty_usd)
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
    _, cut, touched = _score(best, items, penalty_usd)
    cut_by: dict[str, float] = {}
    covered: set[str] = set()
    for a in best:  # attribute each transaction to the first action in the plan that stops it
        amt = sum(i.amount for i in items if a.covers(i) and i.tx_id not in covered)
        covered |= {i.tx_id for i in items if a.covers(i)}
        cut_by[_key(a)] = round(amt, 2)
    return Plan(actions=list(best), exposure_total=total, exposure_cut=round(cut, 2),
                customers_touched=sorted(touched), penalty_usd=penalty_usd, method=method, cut_by_action=cut_by)


def block_everything(items: list[Item], candidates: list[Action], penalty_usd: float = DEFAULT_PENALTY_USD) -> Plan:
    """The comparison: block every card in the ring, which is what a card-by-card response does."""
    cards = [a for a in candidates if a.kind == "card" and any(a.covers(i) for i in items)]
    _, cut, touched = _score(tuple(cards), items, penalty_usd)
    return Plan(actions=cards, exposure_total=round(sum(i.amount for i in items), 2), exposure_cut=round(cut, 2),
                customers_touched=sorted(touched), penalty_usd=penalty_usd, method="block every ring card")
