from types import SimpleNamespace

from redthread.agent.graph import _customer_cards_in_episode, _dataset_id


def test_only_dataset_ids_pass():
    for ok in ["3514948", "C09933-K2", "C09933", "CC-2834"]:
        assert _dataset_id(ok), ok
    for derived in ["C09933-K2|264|50", "D004630", "CASE-HHG-007", "ring 36700632", ""]:
        assert not _dataset_id(derived), derived


def test_r10_counts_only_this_customers_cards_in_the_episode():
    alert = {"card_id": "C00001-K1", "customer_id": "C00001"}
    assessment = SimpleNamespace(connected_card_ids=["C00001-K2", "C09999-K1", "C08888-K1"])
    # own card + the customer's sibling card; other customers' cards are not this customer's exposure
    assert _customer_cards_in_episode(alert, assessment, "fraud") == 2
    assert _customer_cards_in_episode(alert, assessment, "uncertain") == 0
    assert _customer_cards_in_episode(alert, SimpleNamespace(connected_card_ids=["C00001-K2"]), "legitimate") == 0


def test_case_text_sent_to_the_graph_is_bounded():
    """Case writes travel in the URL; an unbounded SAR once failed with 414 Request-URI Too Large."""
    from redthread.agent.memory import MAX_TEXT, _bounded

    long = "x" * 10_000
    for field, limit in MAX_TEXT.items():
        assert len(_bounded(field, long)) <= limit
    assert _bounded("summary", "short") == "short"


def test_a_cross_card_flag_needs_a_card_or_device_behind_it():
    """A report once went to the regulator on a link to "another card's fraud" that named no card."""
    from types import SimpleNamespace

    from redthread.agent.graph import cross_card_backed

    assert not cross_card_backed(SimpleNamespace(connected_card_ids=[], connected_device_ids=[]))
    assert cross_card_backed(SimpleNamespace(connected_card_ids=["C05448-K2"], connected_device_ids=[]))
    assert cross_card_backed(SimpleNamespace(connected_card_ids=[], connected_device_ids=["D004630"]))
