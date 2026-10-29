from redthread.api.replay import replay

TRACE = {
    "alert": {"case_id": "T-1"},
    "events": [{"step": 1, "kind": "alert", "detail": "risk_score: review"},
               {"step": 2, "kind": "evidence", "detail": "query:alert_context(tx=1)"},
               {"step": 3, "kind": "evidence", "detail": "query:card_window(card=C1, 2017-01-01..2017-01-02)"},
               {"step": 4, "kind": "assessment", "detail": "verdict uncertain"},
               {"step": 5, "kind": "reply", "detail": "customer denied"}],
    "evidence": {"alert_context": {"ref": "query:alert_context(tx=1)", "flagged_txn": {"tx_id": "1"}},
                 "card_activity": {"ref": "query:card_window(card=C1, 2017-01-01..2017-01-02)", "rows": [1, 2, 3, 4]}},
    "belief": {"prior": 0.23, "posterior": 0.6, "verdict": "uncertain", "explanation": "prior 0.23; device up",
               "ledger": [{"basis": "device", "direction": "incriminating", "strength": "strong", "lr": 8,
                           "claim": "new device", "counted": True}]},
    "final_assessment": {"verdict": "fraud", "probability": 0.9, "pattern": "card_not_present_new_device"},
    "reply": {"summary": "the customer denied the charge"},
}


def test_each_step_holds_only_the_evidence_collected_so_far():
    steps = replay(TRACE)["steps"]
    assert [len(s["evidence_held"]) for s in steps] == [0, 1, 2, 2, 2]
    assert steps[2]["query"] == "card_window" and steps[2]["parameters"].startswith("card=C1")
    assert steps[2]["returned"]["rows"]["count"] == 4


def test_the_probability_appears_at_the_assessment_and_moves_for_a_stated_reason():
    steps = replay(TRACE)["steps"]
    assert steps[2]["probability"] is None
    assert steps[3]["moved"] == {"from": 0.23, "to": 0.6, "because": "the judged evidence, combined as in the ledger"}
    assert steps[3]["belief"]["counted"][0]["basis"] == "device"
    assert steps[4]["moved"] == {"from": 0.6, "to": 0.9, "because": "the customer denied the charge"}
