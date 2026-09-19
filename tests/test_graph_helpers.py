from types import SimpleNamespace

from redthread.agent.graph import _customer_cards_in_episode, _dataset_id


def test_only_dataset_ids_pass():
    for ok in ["3514948", "C09933-K2", "C09933", "CC-2834"]:
        assert _dataset_id(ok), ok
    for derived in ["C09933-K2|264|50", "D004630", "CASE-HHG-007", "ring 36700632", ""]:
        assert not _dataset_id(derived), derived


def test_r10_counts_only_this_customers_cards_in_the_episode():
    alert = {"card_id": "C00001-K1", "customer_id": "C00001"}
    fraud = SimpleNamespace(verdict="fraud", connected_card_ids=["C00001-K2", "C09999-K1", "C08888-K1"])
    assert _customer_cards_in_episode(alert, fraud) == 2  # own card + sibling card; other customers excluded
    legit = SimpleNamespace(verdict="legitimate", connected_card_ids=["C00001-K2"])
    assert _customer_cards_in_episode(alert, legit) == 0
