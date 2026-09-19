from redthread.policy import Action, Assessment, can_stop, evidence_request, recommend, route_for, sar_required


def actions(recs):
    return [r.action for r in recs]


def base(**kw):
    defaults = dict(verdict="uncertain", probability=0.5, pattern="card_not_present_fraud",
                    exposure_usd=100.0, independent_evidence=1)
    return Assessment(**{**defaults, **kw})


def test_routes():
    assert route_for(Action.CREATE_CASE, 10_000) == "auto"
    assert route_for(Action.DECLINE_TRANSACTION, 1) == "L1"
    assert route_for(Action.BLOCK_CARD, 2_500) == "L1"
    assert route_for(Action.BLOCK_CARD, 2_500.01) == "L2"
    assert route_for(Action.BLOCK_ALL_CARDS, 1) == "L2"
    assert route_for(Action.FILE_REPORT, 1) == "L2"


def test_r1_single_signal_verifies_and_opens_case_never_blocks():
    a = base(probability=0.45, single_signal=True, online=False)
    recs = recommend(a)
    assert actions(recs) == [Action.VERIFY_WITH_CUSTOMER, Action.CREATE_CASE]
    assert evidence_request(a) == "customer_validation"
    assert "R1" in recs[0].reason


def test_3b_example_denial_then_block():
    a = base(probability=0.45, single_signal=True, exposure_usd=300, online=False)
    assert actions(recommend(a, "denied")) == [Action.BLOCK_CARD, Action.CREATE_CASE]


def test_readme_example_card_testing_with_shared_device():
    a = base(verdict="fraud", probability=0.72, pattern="card_testing", exposure_usd=268.43,
             independent_evidence=2, card_testing=True, card_testing_purchase_cleared_over_100=True,
             linked_to_other_fraud=True, connected_cards=("C00877-K1",))
    initial = actions(recommend(a))
    assert initial[0] == Action.DECLINE_TRANSACTION
    assert Action.STEP_UP_AUTH in initial and Action.BLOCK_CARD in initial
    final = recommend(a, "denied")
    assert actions(final) == [Action.BLOCK_CARD, Action.CREATE_CASE, Action.FILE_REPORT,
                              Action.MONITOR_CONNECTED_CARDS]
    assert final[0].route == "L1" and final[2].route == "L2"


def test_r3_confirmation_closes():
    a = base(probability=0.4)
    assert actions(recommend(a, "confirmed")) == [Action.CLOSE_NO_FRAUD]


def test_r4_no_reply_escalates_above_500():
    assert Action.ESCALATE_TO_ANALYST in actions(recommend(base(exposure_usd=600), "no_reply"))
    assert Action.ESCALATE_TO_ANALYST not in actions(recommend(base(exposure_usd=400), "no_reply"))


def test_r7_recurring_dispute_never_blocks():
    a = base(verdict="legitimate", probability=0.1, customer_disputed=True, recurring_match=True,
             independent_evidence=3)
    initial = actions(recommend(a))
    assert initial == [Action.VERIFY_WITH_CUSTOMER, Action.WARN_CUSTOMER, Action.CREATE_CASE]
    assert evidence_request(a) == "customer_validation"
    assert actions(recommend(a, "confirmed")) == [Action.WARN_CUSTOMER, Action.CLOSE_NO_FRAUD]


def test_r6_shared_origin_files_and_monitors():
    a = base(verdict="fraud", probability=0.9, independent_evidence=3, shared_origin=True,
             shared_element="device D004630", connected_cards=("C1-K1", "C2-K1"))
    acts = actions(recommend(a))
    assert {Action.BLOCK_CARD, Action.CREATE_CASE, Action.FILE_REPORT, Action.MONITOR_CONNECTED_CARDS} <= set(acts)
    assert evidence_request(a) is None


def test_r9_undocumented_escalates_and_files():
    a = base(verdict="fraud", probability=0.8, pattern="undocumented", coordinated_undocumented=True,
             independent_evidence=3)
    acts = actions(recommend(a))
    assert {Action.CREATE_CASE, Action.FILE_REPORT, Action.ESCALATE_TO_ANALYST} <= set(acts)


def test_r8_uncertain_and_exposed_escalates():
    assert Action.ESCALATE_TO_ANALYST in actions(recommend(base(exposure_usd=900)))
    assert Action.ESCALATE_TO_ANALYST in actions(recommend(base(evidence_conflicts=True)))


def test_r10_block_all_only_with_two_confirmed_cards():
    a = base(verdict="fraud", probability=0.95, independent_evidence=3, customer_cards_confirmed_fraud=2)
    assert Action.BLOCK_ALL_CARDS in actions(recommend(a))
    b = base(verdict="fraud", probability=0.95, independent_evidence=3, customer_cards_confirmed_fraud=1)
    assert Action.BLOCK_ALL_CARDS not in actions(recommend(b))


def test_confident_legitimate_closes_without_request():
    a = base(verdict="legitimate", probability=0.08, independent_evidence=2)
    assert can_stop(a)
    assert evidence_request(a) is None
    assert actions(recommend(a)) == [Action.CLOSE_NO_FRAUD]


def test_sar_thresholds():
    small = base(verdict="fraud", probability=0.9, exposure_usd=900)
    assert sar_required(small)[0] is False
    assert sar_required(base(verdict="fraud", probability=0.9, exposure_usd=1000.01))[0] is True
    assert sar_required(base(verdict="fraud", probability=0.9, linked_to_other_fraud=True))[0] is True
    assert sar_required(base(verdict="fraud", probability=0.9, exposure_usd=5000), "confirmed")[0] is False


def test_sar_agrees_with_file_report_action():
    for a in [base(verdict="fraud", probability=0.9, exposure_usd=2000, independent_evidence=3),
              base(verdict="fraud", probability=0.9, exposure_usd=200, independent_evidence=3),
              base(probability=0.5, customer_disputed=True, exposure_usd=1500)]:
        for response in [None, "denied", "confirmed", "no_reply"]:
            recs = actions(recommend(a, response))
            if Action.FILE_REPORT in recs:
                assert sar_required(a, response)[0] or a.shared_origin or a.coordinated_undocumented
