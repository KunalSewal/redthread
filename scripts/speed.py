"""Speed and cost per case (challenge 9), from what every answer already records.

    python scripts/speed.py                          # latency and tokens per case
    REDTHREAD_USD_PER_MTOK=0.5 python scripts/speed.py   # and cost, at a stated price

Every answer file carries ``latency_s`` (alert to finished answer), ``tokens`` and ``tool_calls``; the
trace adds how many model calls were reused from an identical earlier call. No price is assumed: a
cost is reported only for a price per million tokens given on the command line's environment, and the
report says which. Output: runs/speed.json.
"""

import json
import os
import statistics

from redthread import paths
from redthread.data import sources


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, max(0, round(q * (len(s) - 1))))]


def main() -> None:
    rows = []
    for path in sorted(sources.answers_dir().glob("HHF-*.json")):
        a = json.loads(path.read_text(encoding="utf-8"))
        trace_path = paths.ROOT / "runs" / f"{path.stem}.trace.json"
        events = json.loads(trace_path.read_text(encoding="utf-8")).get("events", []) if trace_path.exists() else []
        rows.append({"case": path.stem, "latency_s": a["latency_s"], "tokens": a["tokens"],
                     "tool_calls": a["tool_calls"],
                     "model_calls_reused": sum(e["kind"] == "model_reused" for e in events),
                     "model_steps_down": sum(e["kind"] == "model_degraded" for e in events)})
    lat, tok = [r["latency_s"] for r in rows], [r["tokens"] for r in rows]
    price = os.environ.get("REDTHREAD_USD_PER_MTOK")
    summary = {"cases": len(rows), "latency_p50_s": pct(lat, 0.5), "latency_p95_s": pct(lat, 0.95),
               "latency_max_s": max(lat), "tokens_p50": pct(tok, 0.5), "tokens_p95": pct(tok, 0.95),
               "tokens_mean": round(statistics.mean(tok)), "tool_calls_mean": round(statistics.mean(
                   r["tool_calls"] for r in rows), 1)}
    if price:
        summary |= {"usd_per_million_tokens": float(price),
                    "cost_per_case_mean_usd": round(statistics.mean(tok) * float(price) / 1e6, 4),
                    "cost_per_case_p95_usd": round(pct(tok, 0.95) * float(price) / 1e6, 4)}
    (paths.ROOT / "runs" / "speed.json").write_text(json.dumps({"summary": summary, "cases": rows}, indent=1),
                                                    encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
