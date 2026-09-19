import copy
import json
import re

import pytest
from pydantic import ValidationError

from redthread import paths
from redthread.answer import Answer


@pytest.fixture
def readme_example() -> dict:
    text = (paths.DATA / "README.md").read_text(encoding="utf-8")
    block = re.search(r"### Example\s+```json\s+(\{.*?\})\s+```", text, re.S)
    return json.loads(block.group(1))


def test_readme_example_is_valid(readme_example):
    Answer.model_validate(readme_example)


def test_sar_must_match_file_report(readme_example):
    bad = copy.deepcopy(readme_example)
    bad["next_best_actions"]["final"] = [a for a in bad["next_best_actions"]["final"] if a["action"] != "FILE_REPORT"]
    with pytest.raises(ValidationError, match="sar.file"):
        Answer.model_validate(bad)


def test_wrong_route_rejected(readme_example):
    bad = copy.deepcopy(readme_example)
    bad["next_best_actions"]["final"][0]["route"] = "auto"  # BLOCK_CARD is L1 at $268
    with pytest.raises(ValidationError, match="must route L1"):
        Answer.model_validate(bad)


def test_unknown_action_rejected(readme_example):
    bad = copy.deepcopy(readme_example)
    bad["next_best_actions"]["initial"][0]["action"] = "FREEZE_ACCOUNT"
    with pytest.raises(ValidationError):
        Answer.model_validate(bad)


def test_legitimate_has_no_exposure(readme_example):
    bad = copy.deepcopy(readme_example)
    bad["case"]["verdict"] = "legitimate"
    with pytest.raises(ValidationError, match="legitimate"):
        Answer.model_validate(bad)


def test_no_requests_means_final_equals_initial(readme_example):
    bad = copy.deepcopy(readme_example)
    bad["evidence_requests"] = []
    with pytest.raises(ValidationError, match="final must equal initial"):
        Answer.model_validate(bad)


def test_undocumented_needs_description(readme_example):
    bad = copy.deepcopy(readme_example)
    bad["case"]["pattern"] = "undocumented"
    with pytest.raises(ValidationError, match="pattern_description"):
        Answer.model_validate(bad)
