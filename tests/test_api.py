"""Dashboard backend: the alert queue, the case record, and the views built from files.

These run against the repository's real artefacts and skip when the dataset is absent, matching the
other data-dependent tests.
"""

import pytest
from fastapi.testclient import TestClient

from redthread import paths

pytestmark = pytest.mark.skipif(not paths.CASE_PACK_CSV.exists(), reason="dataset not present")


@pytest.fixture(scope="module")
def client() -> TestClient:
    from redthread.api.app import app

    return TestClient(app)


def test_the_queue_merges_the_banks_alerts_with_the_agents_own(client):
    """The six self-raised alerts used to be unreachable: the API read only the case pack."""
    rows = client.get("/api/cases").json()
    sources = {r["source"] for r in rows}
    assert sources == {"bank_queue", "ring_monitor", "model_monitor"}
    assert sum(1 for r in rows if r["source"] == "bank_queue") == 20
    assert sum(1 for r in rows if r["source"] != "bank_queue") >= 1
    assert [r["opened_at"] for r in rows] == sorted(r["opened_at"] for r in rows)


def test_a_self_raised_case_is_retrievable_like_any_other(client):
    body = client.get("/api/cases/MON-001").json()
    assert body["answer"]["case"]["verdict"] in {"fraud", "legitimate", "uncertain"}
    assert body["alert"]["source"] == "ring_monitor"


def test_the_case_record_carries_the_belief_ledger(client):
    body = client.get("/api/cases/HHG-014").json()
    belief = body["belief"]
    assert belief["ledger"] and "posterior" in belief
    assert 0 <= belief["posterior"] <= 1
    # The case file explains the arithmetic, so the prior and its reason must survive the round trip.
    assert belief["prior_reason"]


def test_every_graph_element_knows_when_it_became_known(client):
    """The scrubber rewinds to a step, so a node without one would never appear."""
    graph = client.get("/api/cases/HHG-014").json()["graph"]
    assert graph["nodes"] and graph["steps"] >= 1
    assert all(isinstance(n["step"], int) for n in graph["nodes"])
    assert all(isinstance(e["step"], int) for e in graph["edges"])
    # An edge cannot predate either endpoint.
    steps = {n["id"]: n["step"] for n in graph["nodes"]}
    assert all(e["step"] >= max(steps[e["source"]], steps[e["target"]]) for e in graph["edges"])


def test_monitoring_reports_only_what_the_bank_did_not_raise(client):
    body = client.get("/api/monitoring").json()
    assert body["raised"] == len(body["alerts"])
    assert all(a["source"] != "bank_queue" for a in body["alerts"])
    assert body["confirmed_fraud"] <= body["raised"]


def test_unknown_case_and_ring_are_404(client):
    assert client.get("/api/cases/HHG-999").status_code == 404
    assert client.get("/api/rings/123456789").status_code == 404


def test_a_counterfactual_recomputes_belief_and_the_recommendation(client):
    """Striking a line out must reweigh the ledger, not just divide the odds."""
    base = client.get("/api/cases/HHG-014").json()["belief"]
    body = client.post("/api/cases/HHG-014/counterfactual", json={"dropped": []}).json()
    # Dropping nothing reproduces the original exactly: same engine, same answer.
    assert body["posterior"] == pytest.approx(base["posterior"], abs=0.001)
    assert body["verdict"] == base["verdict"]
    assert body["actions"], "a counterfactual must say what the bank would do"

    # Dropping every incriminating line must not leave belief where it was.
    incriminating = [i for i, x in enumerate(base["ledger"]) if x["direction"] == "incriminating"]
    stripped = client.post("/api/cases/HHG-014/counterfactual",
                           json={"dropped": incriminating}).json()
    assert stripped["posterior"] < base["posterior"]


def test_a_counterfactual_on_a_case_with_no_ledger_is_404(client):
    assert client.post("/api/cases/HHG-999/counterfactual", json={"dropped": []}).status_code == 404
