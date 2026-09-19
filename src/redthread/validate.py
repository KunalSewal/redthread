"""Validate answer files against the schema and the dataset.

    python -m redthread.validate [cases_dir]

Exit code 1 if any file fails. Dataset checks: every transaction, card, customer and closed-case ID
exists; exposure equals the sum of |amount| over affected transactions; every case in the case pack
has exactly one file.
"""

import json
import sys
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from redthread import paths
from redthread.answer import Answer

EXPOSURE_TOLERANCE = 0.01
GRAPH_CASE_PREFIX = "CASE-"  # our own case vertices, written by the agent


@dataclass
class Dataset:
    @cached_property
    def amounts(self) -> pd.Series:
        tx = pd.read_csv(paths.TRANSACTIONS_CSV, usecols=["TransactionID", "TransactionAmt"], engine="pyarrow")
        return tx.set_index(tx["TransactionID"].astype(str))["TransactionAmt"]

    @cached_property
    def cards(self) -> set[str]:
        return set(pd.read_csv(paths.PROCESSED / "cards.csv", usecols=["card_id"])["card_id"])

    @cached_property
    def customers(self) -> set[str]:
        return {c.split("-")[0] for c in self.cards}

    @cached_property
    def _device_table(self) -> pd.DataFrame:
        return pd.read_csv(paths.PROCESSED / "devices.csv", usecols=["device_id", "profile"])

    @cached_property
    def devices(self) -> set[str]:
        return set(self._device_table["profile"])

    @cached_property
    def device_ids(self) -> set[str]:
        return set(self._device_table["device_id"])

    @cached_property
    def closed_cases(self) -> set[str]:
        return set(pd.read_csv(paths.CLOSED_CASES_CSV, usecols=["case_id"])["case_id"])

    @cached_property
    def case_pack(self) -> set[str]:
        return set(pd.read_csv(paths.CASE_PACK_CSV, usecols=["case_id"])["case_id"])

    def known_entity(self, entity_id: str) -> bool:
        return (entity_id in self.amounts.index or entity_id in self.cards or entity_id in self.customers
                or entity_id in self.closed_cases or entity_id in self.devices or entity_id in self.device_ids
                or entity_id.startswith(GRAPH_CASE_PREFIX))


def dataset_errors(answer: Answer, data: Dataset) -> list[str]:
    errors = []
    c = answer.case
    if answer.case_id not in data.case_pack:
        errors.append(f"case_id {answer.case_id} is not in case_pack.csv")
    missing_tx = [t for t in c.affected_txn_ids if t not in data.amounts.index]
    if missing_tx:
        errors.append(f"unknown transaction IDs: {missing_tx}")
    else:
        total = float(data.amounts.loc[c.affected_txn_ids].abs().sum())
        if abs(total - c.exposure_usd) > EXPOSURE_TOLERANCE:
            errors.append(f"exposure_usd {c.exposure_usd} != sum of affected amounts {total:.2f}")
    for label, ids, known in [
        ("card", c.connected_card_ids, data.cards),
        ("device profile", c.connected_device_profiles, data.devices),
        ("closed case", c.similar_prior_cases, data.closed_cases),
    ]:
        unknown = [i for i in ids if i not in known]
        if unknown:
            errors.append(f"unknown {label} IDs: {unknown}")
    unknown_refs = [e for ev in c.evidence for e in ev.entity_ids if not data.known_entity(e)]
    unknown_refs += [s for s in answer.sar.subjects if not data.known_entity(s)]
    if unknown_refs:
        errors.append(f"unknown entity IDs in evidence/SAR: {sorted(set(unknown_refs))}")
    return errors


def validate_dir(cases_dir: Path) -> int:
    data = Dataset()
    files = sorted(cases_dir.glob("*.json"))
    failures = 0
    for f in files:
        try:
            answer = Answer.model_validate(json.loads(f.read_text(encoding="utf-8")))
            errors = dataset_errors(answer, data)
            if f.stem != answer.case_id:
                errors.append(f"file name must be {answer.case_id}.json")
        except (ValidationError, json.JSONDecodeError) as exc:
            errors = [str(exc)]
        status = "ok" if not errors else "FAIL"
        print(f"{status:4} {f.name}")
        for e in errors:
            print(f"     - {e}")
        failures += bool(errors)
    missing = data.case_pack - {f.stem for f in files}
    if cases_dir.name == "cases" and missing:
        print(f"FAIL missing answer files: {sorted(missing)}")
        failures += 1
    print(f"{len(files) - failures}/{len(files)} files valid")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(validate_dir(Path(sys.argv[1]) if len(sys.argv) > 1 else paths.CASES_OUT))
