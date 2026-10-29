from redthread import schemes


def row(tx, ts, amount, product="C", channel="online", device_status=None, proxy=None):
    return {"tx_id": tx, "ts": ts, "amount": amount, "product": product, "channel": channel,
            "device_status": device_status, "proxy": proxy}


PROBES = [row("1", "2017-01-05 11:33:02", 3.51), row("2", "2017-01-07 10:03:06", 5.18),
          row("3", "2017-01-14 14:57:38", 2.66), row("4", "2017-01-26 15:09:37", 2.90)]


def test_the_run_is_every_new_kind_charge_of_the_flagged_ones_kind():
    other_kind = row("9", "2017-01-10 09:00:00", 75.0, product="R")
    run = schemes.flagged_run([*PROBES, other_kind], "4", baseline_txns=60)
    assert [r["tx_id"] for r in run] == ["1", "2", "3", "4"]


def test_no_run_without_history_a_single_charge_or_a_familiar_kind():
    assert schemes.flagged_run(PROBES, "4", baseline_txns=2) == []  # nothing is "new" to a card with no past
    assert schemes.flagged_run(PROBES[-1:], "4", baseline_txns=60) == []  # one unusual purchase is ambiguous
    assert schemes.flagged_run(PROBES[:3], "4", baseline_txns=60) == []  # the flagged charge is not in it


def test_signature_bands_amounts_and_keeps_rare_conditions():
    probes = schemes.signature(PROBES)
    assert probes.probes and (probes.amount_lo, probes.amount_hi) == (0.0, schemes.SMALL_AUTH_USD)
    assert probes.min_txns == 3
    proxied = schemes.signature([row("1", "2017-01-12 07:08:46", 850.28, device_status="New", proxy="ANON"),
                                 row("2", "2017-01-14 20:25:19", 447.95, device_status="New", proxy="ANON")])
    assert not proxied.probes and proxied.need_new_device and proxied.need_proxy
    assert (proxied.amount_lo, proxied.amount_hi) == (358.36, 1062.85)
    assert proxied.min_txns == 2  # a rare signature: two matching charges make a peer


def test_strengths():
    assert schemes.run_strength(PROBES) == "moderate"  # measured: never strong on its own
    assert schemes.run_strength(PROBES[:2]) == "moderate"
    assert schemes.run_strength(PROBES[:1]) is None
    assert schemes.peer_strength(20, [8, 4]) == "strong"  # HHF-004's probes: 20 cards against 8 and 4
    assert schemes.peer_strength(3, [0, 0]) == "moderate"
    assert schemes.peer_strength(108, [143, 134]) is None  # at its usual level: how people shop
    assert schemes.peer_strength(1, [0, 0]) is None


def test_probes_spread_over_weeks_are_not_r5_card_testing():
    assert not schemes.fits_card_testing(PROBES)
    burst = [row("1", "2017-01-14 13:05:30", 1.53), row("2", "2017-01-14 13:14:30", 3.46),
             row("3", "2017-01-14 13:23:30", 3.33), row("4", "2017-01-14 13:57:30", 236.28)]
    assert schemes.fits_card_testing(burst)  # HHF-007: three probes in under an hour, then $236
