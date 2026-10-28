"""The approval ledger: append-only, one decision per action, and tamper-evident.

Each line is one decision. It carries the hash of the line before it and its own hash over its
content, so editing or deleting any earlier decision breaks every hash after it, and ``verify``
names the first broken line. Decisions are never rewritten: a second decision on the same action
is refused.
"""

import hashlib
import json
from pathlib import Path

GENESIS = "0" * 64


def _hash(record: dict) -> str:
    body = {k: v for k, v in record.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


class Ledger:
    def __init__(self, path: Path):
        self.path = path

    def records(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def decisions(self) -> dict[str, dict[str, dict]]:
        """{case_id: {action: record}}, the shape the case views read."""
        out: dict[str, dict[str, dict]] = {}
        for r in self.records():
            out.setdefault(r["case_id"], {})[r["action"]] = r
        return out

    def find(self, case_id: str, action: str) -> dict | None:
        return self.decisions().get(case_id, {}).get(action)

    def append(self, entry: dict) -> dict:
        """Add a decision. Raises ``KeyError`` if this action on this case was already decided."""
        if self.find(entry["case_id"], entry["action"]):
            raise KeyError(f"{entry['action']} on {entry['case_id']} was already decided")
        existing = self.records()
        record = {**entry, "seq": len(existing) + 1, "prev": existing[-1]["hash"] if existing else GENESIS}
        record["hash"] = _hash(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
        return record

    def verify(self) -> tuple[bool, int | None]:
        """(intact, first broken sequence number or None)."""
        prev = GENESIS
        for i, r in enumerate(self.records(), 1):
            if r.get("seq") != i or r.get("prev") != prev or r.get("hash") != _hash(r):
                return False, i
            prev = r["hash"]
        return True, None
