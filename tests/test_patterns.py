from redthread.patterns import card_testing_sequence, classify, home_region


def txn(ts, amount, channel="online", region=None, device_status=None):
    return {"ts": ts, "amount": amount, "channel": channel, "region": region, "device_status": device_status}


def test_no_episode_is_no_pattern():
    assert classify([]) == "none"


def test_mixed_channel_is_account_takeover():
    rows = [txn("2016-11-14 09:00:00", 50, "online"), txn("2016-11-14 12:00:00", 80, "in_person", region="264")]
    assert classify(rows, {"264": 40}) == "account_takeover"


def test_in_person_away_from_home_region():
    rows = [txn("2016-11-14 09:00:00", 80, "in_person", region="433")]
    assert classify(rows, {"264": 40, "433": 1}) == "out_of_region_use"
    assert classify(rows, {"433": 40}) == "account_takeover"  # at home: not out-of-region


def test_online_new_device():
    assert classify([txn("2016-11-14 09:00:00", 80, device_status="New")]) == "card_not_present_new_device"
    assert classify([txn("2016-11-14 09:00:00", 80, device_status="Found")]) == "card_not_present_fraud"


def test_card_testing_beats_other_rules():
    rows = [txn("2016-11-14 09:12:00", 1.10, device_status="New"), txn("2016-11-14 09:30:00", 2.40),
            txn("2016-11-14 09:52:00", 0.95), txn("2016-11-14 10:31:00", 259.98)]
    assert card_testing_sequence(rows)
    assert classify(rows) == "card_testing"


def test_small_amounts_without_a_larger_purchase_are_not_testing():
    rows = [txn("2016-11-14 09:12:00", 1.10), txn("2016-11-14 09:30:00", 2.40), txn("2016-11-14 09:52:00", 0.95)]
    assert not card_testing_sequence(rows)


def test_coordinated_abuse_overrides():
    rows = [txn("2016-11-14 09:00:00", 80, device_status="New")]
    assert classify(rows, coordinated_undocumented=True) == "undocumented"


def test_home_region_ignores_blanks():
    assert home_region({"": 900, "264": 5, "433": 2}) == "264"
    assert home_region({}) is None
