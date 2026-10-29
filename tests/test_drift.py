"""The data layout changes only when a named L2 approver accepts it, and only for the data it was shown."""

import importlib.util
import json
from pathlib import Path

import pytest

from redthread.api import auth
from redthread.api.ledger import Ledger

spec = importlib.util.spec_from_file_location("drift", Path(__file__).parents[1] / "scripts" / "drift.py")
drift = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drift)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    data = tmp_path / "new.csv"
    data.write_text("TransactionID,ts\n1,2017-01-01 00:00:00\n", encoding="utf-8")
    proposal = {"proposal_sha256": "abc123", "breaks": ["months restart at 1"],
                "remap": {"transactions": ["new.csv"]}, "fingerprints": {"new.csv": drift._fingerprint(data)}}
    (tmp_path / "proposal.json").write_text(json.dumps(proposal), encoding="utf-8")
    monkeypatch.setattr(drift, "PROPOSAL", tmp_path / "proposal.json")
    monkeypatch.setattr(drift, "LEDGER", Ledger(tmp_path / "ledger.jsonl"))
    monkeypatch.setattr(drift.sources, "SOURCE_MAP", tmp_path / "config" / "source_map.json")
    monkeypatch.setattr(drift.paths, "ROOT", tmp_path)
    monkeypatch.setenv(auth.APPROVERS_ENV, str(tmp_path / "approvers.json"))
    _, l1 = auth.add("Asha Rao", "L1")
    _, l2 = auth.add("Vikram Sen", "L2")
    return tmp_path, data, l1, l2


def test_an_l1_approver_cannot_change_the_data_layout(env):
    tmp, _, l1, _ = env
    with pytest.raises(SystemExit, match="needs L2"):
        drift.approve(l1, "")
    assert not (tmp / "config" / "source_map.json").exists()


def test_data_that_changed_after_the_proposal_is_refused(env):
    tmp, data, _, l2 = env
    data.write_text("TransactionID,ts\n2,2017-01-02 00:00:00\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="changed since the proposal"):
        drift.approve(l2, "")
    assert not (tmp / "config" / "source_map.json").exists()


def test_an_approval_writes_the_layout_and_the_ledger(env):
    tmp, _, _, l2 = env
    drift.approve(l2, "checked the three breaks")
    layout = json.loads((tmp / "config" / "source_map.json").read_text(encoding="utf-8"))
    assert layout["approved"]["approver"] == "Vikram Sen" and layout["map"] == {"transactions": ["new.csv"]}
    assert drift.LEDGER.verify() == (True, None)
    assert drift.LEDGER.records()[0]["action"] == "abc123"


def test_the_reader_refuses_data_that_was_not_approved(tmp_path, monkeypatch):
    from redthread.data import sources

    new = tmp_path / "data" / "round2" / "transactions_2017q1.csv"
    new.parent.mkdir(parents=True)
    new.write_text("TransactionID,ts\n1,2017-01-01 00:00:00\n", encoding="utf-8")
    monkeypatch.setattr(sources, "_UNAPPROVED", (new,))
    monkeypatch.setattr(sources, "SOURCE_MAP", tmp_path / "config" / "source_map.json")
    monkeypatch.setattr(sources.paths, "ROOT", tmp_path)
    sources._layout.cache_clear()
    try:
        with pytest.raises(sources.DataLayoutError, match="no layout has been approved"):
            sources.transaction_files()
        sources.SOURCE_MAP.parent.mkdir()
        sources.SOURCE_MAP.write_text(json.dumps({
            "map": {"transactions": ["data/round2/transactions_2017q1.csv"]},
            "fingerprints": {"data/round2/transactions_2017q1.csv": drift._fingerprint(new)}}), encoding="utf-8")
        sources._layout.cache_clear()
        assert sources.transaction_files() == [new]
        new.write_text("TransactionID,ts\n9,2017-01-09 00:00:00\n", encoding="utf-8")  # edited after approval
        sources._layout.cache_clear()
        with pytest.raises(sources.DataLayoutError, match="differs from the approved layout"):
            sources.transaction_files()
    finally:
        sources._layout.cache_clear()
