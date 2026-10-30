"""Someone else's schema: parse it without its comments, and reject any mapping it does not support."""

import importlib.util
from pathlib import Path

import pytest

from redthread.schemamap import parse_gsql, strip_comments, validate

ROOT = Path(__file__).parents[1]
BIAN = ROOT / "test_schema" / "bank2_bian_service_domains.gsql"
T24 = ROOT / "test_schema" / "bank3_core_banking_t24.gsql"
pytestmark = pytest.mark.skipif(not BIAN.exists(), reason="test schemas not present")

spec = importlib.util.spec_from_file_location("schema_map", ROOT / "scripts" / "schema_map.py")
schema_map = importlib.util.module_from_spec(spec)
spec.loader.exec_module(schema_map)


def test_the_answer_written_in_the_comments_never_reaches_the_mapper():
    text = BIAN.read_text(encoding="utf-8")
    assert "Expected mapping" in text
    stripped = strip_comments(text)
    assert "Expected mapping" not in stripped and "ground truth" not in stripped and "#" not in stripped


def test_the_schema_is_parsed_with_directions_reverse_names_and_multi_type_edges():
    s = parse_gsql(BIAN.read_text(encoding="utf-8"))
    assert s.graph == "Bank_BIAN" and len(s.vertices) == 16 and len(s.edges) == 21
    plan = s.edges["planCoversFacility"]
    assert plan.pairs == [("CustomerRelationshipManagementPlan", "CurrentAccountFacility"),
                          ("CustomerRelationshipManagementPlan", "SavingsAccountFacility")]
    assert plan.reverse == "reverse_planCoversFacility" and "facilityRole" in plan.attributes
    assert s.hop("reverse_executionDebitsFacility") == [("CurrentAccountFacility", "PaymentExecutionProcedure"),
                                                        ("SavingsAccountFacility", "PaymentExecutionProcedure")]
    t24 = parse_gsql(T24.read_text(encoding="utf-8"))
    assert t24.vertices["CUSTOMER"].attributes["CUSTOMER_NO"] == "INT"


def concept(name, vertices, confidence="exact"):
    return {"concept": name, "vertices": vertices, "filter": "", "confidence": confidence, "reason": "r"}


def test_a_mapping_the_schema_does_not_support_is_rejected_not_patched():
    s = parse_gsql(T24.read_text(encoding="utf-8"))
    good = {"concepts": [concept("Account", ["ACCOUNT"]), concept("Transaction", ["FUNDS_TRANSFER", "TELLER"])],
            "relations": [{"relation": "INITIATED", "confidence": "exact", "reason": "r",
                           "paths": [{"edges": ["reverse_FT_DEBIT_ACCT_NO"], "filter": ""},
                                     {"edges": ["reverse_TT_ACCOUNT_1"], "filter": "DR_CR_MARKER = DEBIT"}]}],
            "attributes": [{"attribute": "Transaction.amount", "sources": ["FUNDS_TRANSFER.DEBIT_AMOUNT",
                            "TELLER.AMOUNT_LOCAL_1"], "transform": "", "confidence": "exact", "reason": "r"}]}
    assert validate(good, s) == []
    wrong_way = {**good, "relations": [{**good["relations"][0], "paths": [{"edges": ["FT_DEBIT_ACCT_NO"],
                                                                            "filter": ""}]}]}
    assert any("does not continue the path" in p for p in validate(wrong_way, s))
    invented = {**good, "concepts": [concept("Account", ["ACCOUNTS"]), *good["concepts"][1:]],
                "attributes": [{**good["attributes"][0], "sources": ["FUNDS_TRANSFER.AMOUNT"]}]}
    problems = validate(invented, s)
    assert any("no such vertex" in p for p in problems) and any("no attribute" in p for p in problems)


def test_the_score_reads_reverse_edges_and_paths_by_the_vertices_they_cross():
    s = parse_gsql(T24.read_text(encoding="utf-8"))
    names = schema_map._names(s)
    key = schema_map.key_elements("ACCOUNT_CUSTOMER and JOINT_HOLDER (both CUSTOMER <- ACCOUNT)", names, s)
    ours = schema_map.our_elements({"paths": [{"edges": ["reverse_ACCOUNT_CUSTOMER"], "filter": ""},
                                              {"edges": ["reverse_JOINT_HOLDER"], "filter": ""}]}, names, s)
    assert key == {"ACCOUNT_CUSTOMER", "JOINT_HOLDER"} and key <= ours
    truth = schema_map.ground_truth(T24.read_text(encoding="utf-8"))
    assert truth["Beneficiary.bank_identifier"]["confidence"] == "exact"  # a single space before the confidence
    assert truth["Merchant"]["confidence"] == truth["InvestigationCase"]["confidence"] == "unmapped"
