# CLAUDE.md — TigerGraph Agentic Fraud Investigation (HHGOA 2026)

Working instructions for Claude and humans on this repo. Keep this file under ~150 lines.
Detail lives in `context/`; read the relevant file there before working in that area.

## What we are building

An AI agent that takes a fraud alert (risk score, customer report, or analyst request),
investigates it against a TigerGraph knowledge graph plus prior closed cases, decides
verdict / pattern / exposure / next best action under the bank's Fraud Policy, requests
(simulated) evidence when uncertain, writes the case back to the graph as memory, and
explains itself. Graded on 20 benchmark cases (`data/case_pack.csv`) against a hidden key.

- Full deliverables checklist and judging weights: `context/deliverables.md`
- Data files, columns, joins, profiling facts: `context/data-dictionary.md`
- Fraud Policy condensed (actions, routes, R1–R10, SAR, stopping): `context/policy-cheatsheet.md`
- Architecture decisions and open questions: `context/decisions.md`
- Build plan, architecture diagram, and progress: `context/plan.md`
- Authoritative sources (do not edit): `data/README.md` (task, policy, answer format),
  `TigerGraph Agentic Fraud Investigation Problem Statement.docx`, the two briefing `.md` files at root.

## Hard rules (disqualification or zero-score risks)

1. **Never use the original public IEEE-CIS / Kaggle files** to recover labels. Disqualification.
2. **Every ID in an answer file must exist in this dataset.** Made-up IDs score zero. Validate IDs
   against the data before writing any answer file.
3. **Action names and routes must be the exact policy identifiers** (`BLOCK_CARD`, `L1`, ...).
   Routes are computed deterministically from policy, never chosen by the LLM.
4. **`sar.file` must agree with `FILE_REPORT` in `next_best_actions.final`.**
5. **Risk score is an input, never a verdict.** Above 0.7 most are legitimate; some fraud scores ~0.
   Half the benchmark cases are legitimate. Blocking on one signal with p < 0.70 breaches R1.
6. **Missing fields score zero.** Every answer file must pass schema validation.
7. **The LLM reasons, selects tools, synthesizes and explains. Graph analysis is done in GSQL.**
   Do not have the LLM "eyeball" raw rows in place of a query.
8. **`customer_id` is an issuer bucket, not a person.** Judge "normal for this cardholder" at the
   `Holder` level (see `context/data-dictionary.md`). Weight device links by device specificity.
9. **No benchmark-artifact signals.** Only evidence an analyst could defend.

## Data handling (the 708 MB CSV)

- **Never Read `data/transactions.csv` or `data/identity.csv` with the Read tool or `cat`.**
  Use pandas/pyarrow with `usecols=` / `nrows=` / chunking, and print only aggregates or a few rows.
- `data/` CSVs are git-ignored and must never be committed.
- For column meanings, use `context/data-dictionary.md` instead of opening the file.
- Answers to scored cases come from the agent pipeline, not from hand analysis pasted into files.
  Hand investigation is for designing queries and tests only.

## Required stack (from the problem statement)

- TigerGraph (Savanna or Community Edition 4.2+) for graph **and** vector storage.
- GSQL queries + TigerGraph graph algorithms for pattern detection. What we actually run:
  our own connected-components pass (`ring_wcc`, tuned to new-to-account device use and measured)
  and the GDS library's `tg_louvain` for communities, surfaced to the agent by the `community` tool.
  `tg_pagerank` and `tg_jaccard_nbor_ss` are installed from the library but not run in batch:
  PageRank takes a single vertex type and our card-device projection is bipartite. Do not describe
  an algorithm as used unless it runs.
- TigerGraph MCP (`tigergraph-mcp`, official repo `tigergraph/tigergraph-mcp`) as the agent's tool surface.
- GraphRAG: graph evidence + retrieved policy/typology/closed-case text passed to the LLM as context.
- A UI showing investigation, case progression, evidence, uncertainty, and next actions.
- Agent framework and LLM are our choice (see `context/decisions.md`).

## Gotchas learned the hard way (TigerGraph / Savanna)

- Reserved words cannot be attribute or parameter names: `proxy`, `target`, `at` (renamed).
- REST uploads ignore `HEADER="true"`: `load_file` strips the header; jobs use positional columns
  generated from the CSV header (`$"name"` needs a fixed file path at job creation).
- Empty `MaxAccum` prints -1.797e308, which breaks strict JSON parsers (the MCP server): initialise it.
  `PRINT vertexSet` includes every vertex accumulator; project attributes instead.
- Set-valued query parameters cannot be empty (arrive as NULL): write edges one call at a time.
- Schema changes disable affected loading jobs: rerun `setup_graph.py jobs` after one.
- Savanna free tier auto-suspends; everything is resumable. Stop the workspace when done (credits).
- Writing Python source from a shell heredoc: a non-raw string containing `` becomes a literal
  backspace (0x08) in the file, silently breaking a regex. This has bitten us twice. Write such
  edits with the Write/Edit tools, and scan with
  `python -c "d=open(f,'rb').read(); print([i for i,b in enumerate(d) if b<9])"`.

## Engineering practices

- **Python 3.12** (already on this machine via miniconda). Pin dependencies in `requirements.txt`
  or `pyproject.toml`. Secrets in `.env` (git-ignored); commit a `.env.example` instead.
- **Deterministic core, LLM at the edges.** Policy routing, exposure sums, SAR/route consistency,
  and ID validation are plain Python functions with unit tests. The LLM does not do arithmetic
  or pick routes.
- **Least-privilege graph access for the agent.** Prefer installed, parameterized GSQL queries.
  The MCP `gsql` tool can drop graphs; do not give the agent unrestricted write access.
  Case write-back goes through one dedicated upsert query.
- **Tests before claims.** Unit tests for policy engine and answer builder; a schema validator for
  `cases/*.json`; a smoke test that runs one case end-to-end. Run them before saying something works.
- **Reproducibility.** Loading, schema creation, and query installation are scripts, not manual
  GraphStudio clicks. A fresh clone plus `.env` must be able to rebuild the graph.
- **Record every tool call, token count, and latency per case.** They are required answer fields.
- Small, focused commits with descriptive messages. Commit only when asked.
- Match surrounding code style; no speculative abstractions.

## Repo layout (update this section when it changes)

```
cases/                 # 20 graded answer files, <case_id>.json  (SUBMISSION)
cases_extra/           # optional: self-monitored alerts beyond the 20 (Innovation credit)
context/               # reference docs for Claude and the team
data/                  # provided dataset (CSVs + data/processed git-ignored, README tracked)
docs/regulatory/       # downloaded FinCEN/FFIEC/FATF docs for GraphRAG (git-ignored)
gsql/                  # 01 schema, 01b-d schema changes, 02 loading jobs, 03 installed queries
scripts/               # prepare_data, train_model, setup_graph, build_knowledge, run_cases
src/redthread/agent/   # workflow (graph.py), MCP client, tools, prompts, simulator, memory, llm
src/redthread/api/     # FastAPI dashboard backend
src/redthread/         # policy.py, answer.py, validate.py, model/, rag/, data/
runs/                  # investigation traces + approvals (git-ignored)
ui/                    # React dashboard (Vite)
tests/
```

## Status

See `context/decisions.md` for the current decision log. Update the Status line below at the end of
each work session.

- **Status (2026-09-21):** All 20 answers valid: 10 fraud, 9 legitimate, 1 `uncertain` (HHG-004, the
  first to reach an answer file). On 60 replayed closed cases with the trigger decoupled from the
  outcome: verdict accuracy 75%, Brier 0.277, cleared cases left alone 80%, wrongly accused customers
  down 17 to 6, missed fraud 7 to 3, 17 left `uncertain`; by trigger 80% (customer reports) against
  68% (model alerts). Numbers: `runs/backtest_final.json`, matched "before" in
  `runs/backtest_after.json` (same seed).
  **Never quote the old backtest (24/24, Brier 0.005)** — that harness set the trigger from the
  outcome. Three root causes are written up in `context/decisions.md` (correlated evidence, a
  circular simulated reply, and policy rules fetched by vector search).
  Workbench rebuilt: 5 routes, thread-as-scrubber, live counterfactuals, `?replay=1` presenter mode,
  AA contrast, keyboard and 390px passes. README, blog, demo script and social drafts rewritten
  against the real numbers.
  `cases_extra/` now holds 25 self-raised alerts, all valid: 14 fraud, 11 `uncertain`, $3,900 of
  exposure, 13 reports; the bank had scored 19 of the 25 below 0.30.
  **Remaining:** (1) re-run the model comparison on the fixed harness or keep the
  README's "unverified" caveat; (2) consider calibrating the model's own strength labels (84 "strong",
  19 "decisive" across the backtest); (3) nothing is committed — the owner asked to be asked first;
  (4) owner records the demo (`docs/demo-script.md`) and publishes blog + social post.

## Commands

All commands from the repo root, using the project venv (`.venv`, Python 3.12).

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # setup
.venv/Scripts/python scripts/train_model.py     # ~4 min; writes data/processed/txn_scores.csv
.venv/Scripts/python scripts/prepare_data.py    # ~1 min; writes data/processed/*.csv (needs scores)
.venv/Scripts/python -m pytest -q               # tests (data tests skip if data/ is absent)
.venv/Scripts/ruff check src tests scripts      # lint
.venv/Scripts/python -m redthread.validate cases   # validate answer files
.venv/Scripts/python scripts/setup_graph.py all      # schema, jobs, load, queries (idempotent)
.venv/Scripts/python scripts/setup_graph.py status   # vertex/edge counts
.venv/Scripts/python scripts/setup_graph.py queries --only <name> ...   # reinstall edited queries
.venv/Scripts/python scripts/build_knowledge.py --fetch   # GraphRAG chunks + embeddings -> graph
.venv/Scripts/python scripts/run_cases.py [HHG-001 ...]   # investigate; writes cases/ and runs/
.venv/Scripts/python -m uvicorn redthread.api.app:app --port 8000   # dashboard API
cd ui && npx vite                                     # dashboard at http://localhost:5173
```
