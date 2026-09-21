"""Episode assembly and policy grounding: the deterministic parts of what the agent concludes."""

from types import SimpleNamespace

from redthread.agent.graph import _linking_devices, _needs_resolving, _with_testing_sequence


def ledger(tx_ids):
    return SimpleNamespace(txns={t: {"ts": f"2016-11-14 09:{i:02d}:00"} for i, t in enumerate(tx_ids)},
                           devices={"D000731": "SAMSUNG | Android | chrome | 1920x1080"})


def test_card_testing_small_auths_join_the_episode():
    """R5 only fires if the small authorisations are in the episode; the model usually lists only the
    large purchase it was alerted on."""
    evidence = {"card_activity": {"card_testing_sequences": [
        {"small_auths": ["1", "2", "3"], "followed_by": ["4"], "purchase_over_100_cleared": True}]}}
    assert _with_testing_sequence(["4"], evidence, ledger(["1", "2", "3", "4"])) == ["4", "1", "2", "3"]


def test_testing_sequence_that_does_not_overlap_is_left_alone():
    evidence = {"card_activity": {"card_testing_sequences": [
        {"small_auths": ["1", "2", "3"], "followed_by": ["4"], "purchase_over_100_cleared": False}]}}
    assert _with_testing_sequence(["9"], evidence, ledger(["1", "2", "3", "4", "9"])) == ["9"]


def test_no_episode_stays_empty():
    assert _with_testing_sequence([], {"card_activity": {"card_testing_sequences": []}}, ledger([])) == []


def test_linking_devices_need_sharing_and_specificity():
    shared_specific = {"device_check": {"device": {"device_id": "D000731", "profile_specificity": "specific",
                                                   "ring_id": -1}, "cards_new_device_in_window": 4}}
    assert _linking_devices({"evidence": shared_specific}, ledger([])) == ["D000731"]

    generic = {"device_check": {"device": {"device_id": "D000731", "ring_id": -1,
                                           "profile_specificity": "generic (shared by many unrelated people)"},
                                "cards_new_device_in_window": 40}}
    assert _linking_devices({"evidence": generic}, ledger([])) == []

    alone = {"device_check": {"device": {"device_id": "D000731", "profile_specificity": "specific", "ring_id": -1},
                              "cards_new_device_in_window": 1}}
    assert _linking_devices({"evidence": alone}, ledger([])) == []


def test_a_ring_device_links_even_without_several_new_devices():
    ring = {"device_check": {"device": {"device_id": "D000731", "profile_specificity": "specific", "ring_id": 12},
                             "cards_new_device_in_window": 1}}
    assert _linking_devices({"evidence": ring}, ledger([])) == ["D000731"]


def test_uncertain_belief_is_resolved_once():
    assert _needs_resolving({"belief": {"posterior": 0.5}}) == "resolve_uncertainty"
    assert _needs_resolving({"belief": {"posterior": 0.5}, "resolve_rounds": 1}) == "decide_initial"
    assert _needs_resolving({"belief": {"posterior": 0.93}}) == "decide_initial"
    assert _needs_resolving({"belief": {"posterior": 0.05}}) == "decide_initial"
