"""Writing an investigation's results: the answer, its trace, or the record of a halt.

One place, so the runner, the monitor and the dashboard write the same files the same way, every
string passes through redaction first, and a successful run clears any earlier halt record.
"""

import json
from pathlib import Path

from redthread.agent.graph import TRACE_KEYS, InvestigationHalted, halt_record
from redthread.redact import redact_obj


def persist(state: dict, answer_dir: Path, trace_dir: Path) -> dict:
    """Write the answer and the trace for a completed investigation. Returns the answer as written."""
    case_id = state["alert"]["case_id"]
    answer = redact_obj(state["answer"])
    answer_dir.mkdir(parents=True, exist_ok=True)
    trace_dir.mkdir(parents=True, exist_ok=True)
    (answer_dir / f"{case_id}.json").write_text(json.dumps(answer, indent=2), encoding="utf-8")
    trace = redact_obj({k: state.get(k) for k in TRACE_KEYS})
    (trace_dir / f"{case_id}.trace.json").write_text(json.dumps(trace, indent=1, default=str), encoding="utf-8")
    (trace_dir / f"{case_id}.halted.json").unlink(missing_ok=True)
    return answer


def persist_halt(alert: dict, exc: InvestigationHalted, trace_dir: Path) -> Path:
    """Record a halt. The case's previous answer, if any, is deliberately left as it was."""
    trace_dir.mkdir(parents=True, exist_ok=True)
    path = trace_dir / f"{alert['case_id']}.halted.json"
    path.write_text(json.dumps(redact_obj(halt_record(alert, exc)), indent=1, default=str), encoding="utf-8")
    return path
