from redthread.containment import Action, Item, block_everything, plan

# A device ring: three fraud cards reached through device D1. Card C3 is a busy shared bucket card.
ITEMS = [Item("t1", "C1", 400.0, frozenset({"device:D1"})), Item("t2", "C2", 300.0, frozenset({"device:D1"})),
         Item("t3", "C3", 200.0, frozenset({"device:D1"})), Item("t4", "C3", 50.0)]
CANDIDATES = [Action("card", "C1", frozenset()), Action("card", "C2", frozenset({"P9"})),
              Action("card", "C3", frozenset({"P1", "P2", "P3", "P4"})),
              Action("device", "device:D1", frozenset({"P5"}))]


def test_blocking_the_shared_device_beats_blocking_every_card():
    best = plan(ITEMS, CANDIDATES, penalty_usd=100)
    assert [(a.kind, a.target) for a in best.actions] == [("device", "device:D1")]
    assert best.exposure_cut == 900.0 and best.exposure_left == 50.0
    assert best.customers_touched == ["P5"] and best.net == 800.0
    everything = block_everything(ITEMS, CANDIDATES, penalty_usd=100)
    assert everything.exposure_cut == 950.0 and len(everything.customers_touched) == 5
    assert best.net > everything.net


def test_a_card_whose_loss_does_not_pay_for_the_people_it_touches_is_left_alone():
    # t4 ($50) is only stoppable by blocking C3, which touches four people: not worth it at $100 each.
    best = plan(ITEMS, CANDIDATES, penalty_usd=100)
    assert all(a.target != "C3" for a in best.actions)
    # With no penalty the planner takes everything it can.
    free = plan(ITEMS, CANDIDATES, penalty_usd=0)
    assert free.exposure_cut == 950.0


def test_ties_go_to_the_smaller_plan_and_nothing_useless_is_chosen():
    items = [Item("t1", "C1", 100.0, frozenset({"device:D1"}))]
    cands = [Action("card", "C1", frozenset()), Action("device", "device:D1", frozenset()),
             Action("card", "C9", frozenset())]
    best = plan(items, cands)
    assert len(best.actions) == 1 and best.exposure_cut == 100.0


def test_greedy_is_used_for_large_rings_and_still_attributes_every_dollar():
    items = [Item(f"t{i}", f"C{i}", 10.0 + i) for i in range(20)]
    cands = [Action("card", f"C{i}", frozenset({f"P{i}"} if i % 2 else set())) for i in range(20)]
    best = plan(items, cands, penalty_usd=15)
    assert best.method.startswith("greedy")
    chosen = {a.target for a in best.actions}
    assert {f"C{i}" for i in range(0, 20, 2)} <= chosen  # untouched cards always pay
    assert sum(best.as_dict()["actions"][k]["cuts_usd"] for k in range(len(best.actions))) == best.exposure_cut
