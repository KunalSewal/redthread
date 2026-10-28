"""Approvals are enforced on the server, from an identity the server issued, and are final.

These are the checks the final round's drills probe: an approval attempted by the wrong role, a role
claimed in the request body, and an approval edited after the fact.
"""

import json

import pytest
from fastapi.testclient import TestClient

from redthread.api import auth
from redthread.api.ledger import Ledger
from redthread.data import sources

pytestmark = pytest.mark.skipif(not (sources.paths.ROOT / "cases" / "HHG-019.json").exists(),
                                reason="Round 1 answers not present")
CASE = "HHG-019"  # BLOCK_CARD routed L1, FILE_REPORT routed L2


@pytest.fixture()
def env(tmp_path, monkeypatch):
    from redthread.api import app as app_module

    monkeypatch.setenv(sources.ROUND_ENV, "r1")
    monkeypatch.setenv(auth.APPROVERS_ENV, str(tmp_path / "approvers.json"))
    monkeypatch.setattr(app_module, "APPROVALS", Ledger(tmp_path / "approvals.log.jsonl"))
    monkeypatch.setattr(app_module, "_record_decision_in_graph", lambda *a, **k: False)
    _, lead = auth.add("Asha Rao", "L1")
    _, manager = auth.add("Vikram Sen", "L2")
    return TestClient(app_module.app), {"L1": lead, "L2": manager}, app_module


def post(client, key, **body):
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    return client.post(f"/api/cases/{CASE}/approvals", json=body, headers=headers)


def test_no_key_and_a_wrong_key_are_refused(env):
    client, _, _ = env
    assert post(client, None, action="BLOCK_CARD", decision="approved").status_code == 401
    assert post(client, "not-a-key", action="BLOCK_CARD", decision="approved").status_code == 401


def test_a_role_claimed_in_the_body_is_refused_not_trusted(env):
    """The brief: 'A role read from the request body is not enforcement.'"""
    client, keys, _ = env
    r = post(client, keys["L1"], action="FILE_REPORT", decision="approved", role="L2", approver="Someone")
    assert r.status_code == 422


def test_a_team_lead_cannot_approve_a_filing(env):
    client, keys, _ = env
    r = post(client, keys["L1"], action="FILE_REPORT", decision="approved")
    assert r.status_code == 403 and "L2" in r.json()["detail"]


def test_the_approver_on_record_comes_from_the_key(env):
    client, keys, _ = env
    r = post(client, keys["L1"], action="BLOCK_CARD", decision="approved")
    assert r.status_code == 200
    assert r.json()["approver"] == "Asha Rao" and r.json()["role"] == "L1"
    assert client.get("/api/whoami", headers={"Authorization": f"Bearer {keys['L2']}"}).json() == {
        "name": "Vikram Sen", "role": "L2"}


def test_a_decision_is_final(env):
    client, keys, _ = env
    assert post(client, keys["L2"], action="FILE_REPORT", decision="approved").status_code == 200
    again = post(client, keys["L2"], action="FILE_REPORT", decision="rejected")
    assert again.status_code == 409


def test_the_ledger_shows_any_edit_after_the_fact(env, tmp_path):
    client, keys, app_module = env
    post(client, keys["L1"], action="BLOCK_CARD", decision="approved")
    post(client, keys["L2"], action="FILE_REPORT", decision="approved")
    assert client.get("/api/approvals/verify").json() == {"intact": True, "first_broken_record": None, "records": 2}
    log = tmp_path / "approvals.log.jsonl"
    lines = log.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["decision"] = "rejected"  # someone edits the first decision in place
    log.write_text("\n".join([json.dumps(first, sort_keys=True), *lines[1:]]) + "\n", encoding="utf-8")
    assert app_module.APPROVALS.verify() == (False, 1)


def test_keys_are_never_stored(env, tmp_path):
    _, keys, _ = env
    stored = (tmp_path / "approvers.json").read_text(encoding="utf-8")
    assert keys["L1"] not in stored and keys["L2"] not in stored
