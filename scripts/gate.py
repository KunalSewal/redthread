"""The quality gate: every check, one command, a non-zero exit if any fails.

    python scripts/gate.py              # all checks on the final round's answers in cases/
    python scripts/gate.py --quick      # skip the slow ID and arithmetic pass over the transactions

1. ruff over src, tests and scripts
2. the full test suite
3. our schema and dataset validation of every answer for the current case pack
4. our policy and point-in-time audit (scripts/check_policy.py)
5. the organisers' grader (data/round2/grader/grade.py), with ID and arithmetic checks
6. accuracy of the Round 1 answers against their now-known outcomes (a regression signal)

Writes runs/gate.json so a result can be quoted with its evidence. Nothing here edits an answer.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
R2 = ROOT / "data" / "round2"


def run(name: str, cmd: list[str]) -> dict:
    start = time.time()
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-6:]
    status = "PASS" if proc.returncode == 0 else "FAIL"
    print(f"{status}  {name:34} {time.time() - start:5.0f}s  {tail[-1] if tail else ''}")
    return {"check": name, "ok": proc.returncode == 0, "secs": round(time.time() - start, 1), "tail": tail}


def official_grader(pack: Path, answers: Path, transactions: Path | None) -> dict:
    """The organisers' grader on our answers, laid out the way it expects (teams/<team>/cases/)."""
    with tempfile.TemporaryDirectory() as tmp:
        cases = Path(tmp) / "teams" / "redthread" / "cases"
        cases.mkdir(parents=True)
        ids = pd.read_csv(pack)["case_id"]
        for cid in ids:
            if (answers / f"{cid}.json").exists():
                shutil.copy(answers / f"{cid}.json", cases / f"{cid}.json")
        report = Path(tmp) / "report.json"
        cmd = [PY, "-I", str(R2 / "grader" / "grade.py"), "--teams-dir", str(Path(tmp) / "teams"),
               "--case-pack", str(pack), "--out", str(report)]
        if transactions:
            cmd += ["--transactions", str(transactions)]
        start = time.time()
        subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True)
        team = json.loads(report.read_text())["teams"]["redthread"]
    findings = [(cid, f) for cid, c in team["cases"].items() for f in c["findings"] if f[0] != "warning"]
    ok = team["cases_answered"] == len(ids) and not findings
    print(f"{'PASS' if ok else 'FAIL'}  {'official grader':34} {time.time() - start:5.0f}s  "
          f"answered {team['cases_answered']}/{len(ids)}, hard {team['hard']}, policy {team['policy']}, "
          f"clean {team['clean']}/{len(ids)}")
    for cid, f in findings:
        print(f"        {cid} {f[0]} {f[1]}: {f[2][:110]}")
    return {"check": "official grader", "ok": ok, "answered": team["cases_answered"], "hard": team["hard"],
            "policy": team["policy"], "clean": team["clean"], "findings": [[c, *f] for c, f in findings]}


def round1_accuracy() -> dict:
    """Our Round 1 answers against the outcomes the final round published as CC-5566..5585."""
    closed = pd.read_csv(R2 / "closed_cases_history.csv")
    pack = pd.read_csv(ROOT / "data" / "case_pack.csv")
    folder = ROOT / "cases_round1" if (ROOT / "cases_round1").exists() else ROOT / "cases"
    rows = []
    for p in pack.itertuples():
        f = folder / f"{p.case_id}.json"
        truth = closed[closed["analyst_notes"].str.startswith(f"Case {p.case_id} ", na=False)]
        if not f.exists() or truth.empty:
            continue
        verdict = json.loads(f.read_text(encoding="utf-8"))["case"]["verdict"]
        outcome = truth.iloc[0]["outcome"]
        rows.append({"case": p.case_id, "verdict": verdict, "truth": outcome,
                     "right": (verdict == "fraud") == (outcome == "confirmed_fraud") and verdict != "uncertain",
                     "innocent_harmed": outcome == "cleared" and verdict == "fraud"})
    df = pd.DataFrame(rows)
    out = {"check": "round 1 accuracy", "ok": True, "n": len(df),
           "verdicts_right": int(df["right"].sum()) if len(df) else 0,
           "innocent_customers_harmed": int(df["innocent_harmed"].sum()) if len(df) else 0}
    print(f"INFO  {'round 1 accuracy (regression)':34}        {out['verdicts_right']}/{out['n']} right, "
          f"{out['innocent_customers_harmed']} innocent customer(s) harmed")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="skip the transaction ID/arithmetic pass")
    args = parser.parse_args()
    pack = R2 / "cases" / "case_pack_final.csv"
    results = [
        run("ruff", [PY, "-m", "ruff", "check", "src", "tests", "scripts"]),
        run("tests", [PY, "-m", "pytest", "-q"]),
        run("schema and dataset validation", [PY, "-m", "redthread.validate", "cases"]),
        run("policy and point-in-time audit", [PY, "scripts/check_policy.py", "cases"]),
        official_grader(pack, ROOT / "cases", None if args.quick else R2 / "transactions_2017q1.csv"),
        round1_accuracy(),
    ]
    (ROOT / "runs").mkdir(exist_ok=True)
    (ROOT / "runs" / "gate.json").write_text(json.dumps(
        {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "results": results}, indent=1), encoding="utf-8")
    failed = [r["check"] for r in results if not r["ok"]]
    print("\nGATE " + ("PASSED" if not failed else f"FAILED: {', '.join(failed)}"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
