# RedThread

**An agentic fraud investigator on TigerGraph.** RedThread takes a fraud alert (a model score, a
customer complaint or an analyst's request), investigates it across a knowledge graph of 590k card
transactions, decides what happened and what the bank should do under its fraud policy, asks for more
evidence when the picture is uncertain, and writes every case back into the graph as memory for the
next investigation.

Built for the TigerGraph Agentic Fraud Investigation challenge (Hacker House Goa 2026).

## What it does

```
alert ──► gather evidence ──► investigate ──► assess ──► policy: initial actions
          (fixed checklist)   (LLM picks     (LLM, IDs     │
                               follow-ups)    verified)    ├─ evidence needed? ─► ask customer / step-up
                                                           │                     (simulated reply,
                                                           │                      Bayesian update)
                                                           ▼
                            case memory ◄── report + SAR ◄── policy: final actions
                            (graph)
```

- **Graph evidence through TigerGraph MCP.** The agent reaches TigerGraph only through the official
  [`tigergraph-mcp`](https://github.com/tigergraph/tigergraph-mcp) server, started with a tool
  allowlist: installed queries and vector search, nothing that can change the schema or delete data.
- **Investigation queries in GSQL** (`gsql/03_queries.gsql`): alert context, card windows, holder
  baselines, device neighbourhoods, a shared-origin (policy R6) detector, linked cases, and ring
  detection by connected components over suspicious device use.
- **GraphRAG**: policy rules, fraud patterns, FinCEN/FFIEC/FATF guidance and 5,565 closed-case
  narratives are embedded into TigerGraph's vector store; retrieval is a vector search followed by graph
  traversal to the cards and devices each hit touched.
- **A calibrated fraud model**: LightGBM trained on the closed cases (October holdout AUC 0.968 vs 0.866
  for the bank's score), stored on every transaction as evidence, never as a verdict.
- **Policy as code** (`src/redthread/policy.py`): rules R1–R10, approval routes, SAR criteria and the
  stopping rule are deterministic and unit-tested. The LLM never chooses an approval route.
- **Case memory**: each investigation becomes a `FraudCase` vertex with edges to its transactions,
  cards, devices and similar prior cases, a step-by-step timeline, and an embedding.

## What we found in the data

- `customer_id` is an issuer bucket shared by many people, so "normal for this customer" is meaningless
  at that level. RedThread resolves **account holders** (card + billing region + days since first use)
  and judges behaviour per holder.
- The closed cases label essentially all fraud from July to October, which made a proper fraud model
  trainable. The bank's risk score is right about 37% of the time above 0.85; ours about 92%.
- An **undocumented pattern**: one Samsung device profile, always new to the account and behind an
  anonymous proxy, shows up across dozens of unrelated cards. Ring detection isolates it without
  chaining through popular phones that thousands of people share.

## Repository layout

| Path | What |
|---|---|
| `src/redthread/agent/` | the agent: workflow, MCP client, tools, prompts, simulator, memory |
| `src/redthread/policy.py` | Fraud Policy v1.0 as code |
| `src/redthread/answer.py`, `validate.py` | answer-file schema and dataset checks |
| `src/redthread/model/` | fraud model features and score calibration |
| `gsql/` | schema, vector attributes, loading jobs, installed queries |
| `scripts/` | data prep, model training, graph setup, knowledge base, case runner |
| `cases/` | the 20 answer files |
| `context/` | design notes, data dictionary, decisions |

## Running it

Requirements: Python 3.12, a TigerGraph 4.2+ workspace (Savanna or Community Edition), a Gemini API key.

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
cp .env.example .env                              # fill in TigerGraph and Gemini credentials
# put the dataset CSVs in data/

python scripts/train_model.py                     # fraud model + scores        (~4 min)
python scripts/prepare_data.py                    # vertex/edge files           (~1 min)
python scripts/setup_graph.py all                 # schema, load, queries       (~10 min)
python scripts/setup_graph.py queries --only ring_wcc && \
  python -c "from redthread.tg import connection; print(connection().runInstalledQuery('ring_wcc'))"
python scripts/build_knowledge.py --fetch         # GraphRAG knowledge base
python scripts/run_cases.py                       # investigate all 20 cases -> cases/
python -m redthread.validate cases                # check every answer file
```

`python -m pytest` runs the unit tests (policy engine, answer schema, card-ID derivation, simulator, tools).
