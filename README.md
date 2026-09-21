# RedThread

**An agentic fraud investigator on TigerGraph.** RedThread takes a fraud alert — a model score, a
customer complaint, or an analyst's request — investigates it across a knowledge graph of 590,000 card
transactions, decides what happened and what the bank should do under its fraud policy, asks for more
evidence when the picture is uncertain, and writes every case back into the graph as memory for the
next investigation.

Built for the TigerGraph Agentic Fraud Investigation challenge (Hacker House Goa 2026).

## What it does

```
alert ──► gather evidence ──► investigate ──► weigh ──► policy: initial actions
          (fixed checklist)   (LLM picks     (code does    │
                               follow-ups)    the maths)   ├─ uncertain? ─► ask the customer / step up
                                                           │                (simulated reply; moves
                                                           │                 belief only if it adds
                                                           │                 information)
                                                           ▼
                            case memory ◄── report + SAR ◄── policy: final actions
                            (graph)
```

- **Graph access through TigerGraph MCP.** The agent reaches TigerGraph only through the official
  [`tigergraph-mcp`](https://github.com/tigergraph/tigergraph-mcp) server, started with a tool
  allowlist: installed queries and vector search, nothing that can change the schema or delete data.
- **Investigation queries in GSQL** (`gsql/03_queries.gsql`, 21 installed queries): alert context,
  card windows, holder baselines, device neighbourhoods, a shared-origin detector for policy R6,
  linked cases, ring membership and community profiles.
- **Graph algorithms.** Ring detection is our own connected-components pass over *suspicious,
  new-to-account* device use — tuned so it finds nine tight rings instead of one 118-card blob
  formed by chaining through popular phones. On top of it, TigerGraph's GDS `tg_louvain` runs over
  the card–device graph weighted by transaction count, and the agent reads the result through a
  `community` tool. `tg_pagerank` and `tg_jaccard_nbor_ss` are installed but not run in batch: this
  release of PageRank takes a single vertex type and our projection is bipartite, and device
  centrality is already stored as `DeviceProfile.n_cards`.
- **GraphRAG.** Policy rules, fraud patterns, FinCEN/FFIEC/FATF/OFAC guidance and 5,565 closed-case
  narratives are embedded into TigerGraph's vector store. Retrieval is a vector search followed by
  graph traversal to the cards and devices each hit touched, and a citation can be opened and read in
  full in the interface.
- **A calibrated fraud model.** LightGBM trained on the closed cases (October holdout AUC 0.968
  against 0.866 for the bank's own score), stored on every transaction as evidence, never as a verdict.
- **Policy as code** (`src/redthread/policy.py`). Rules R1–R10, approval routes, SAR criteria and the
  stopping rule are deterministic and unit-tested. The LLM never chooses an approval route and never
  does arithmetic.
- **An auditable belief ledger** (`src/redthread/belief.py`). The model judges each finding — which
  way it points, how strong it is, and what it rests on — and the code does the Bayes. Every
  probability can be replayed, and any line can be struck out to see what the agent would have
  concluded without it.
- **Case memory.** Each investigation becomes a `FraudCase` vertex with edges to its transactions,
  cards, devices and similar prior cases, a step-by-step timeline, and an embedding.

## What we found in the data

- `customer_id` is an issuer bucket shared by many unrelated people, so "normal for this customer" is
  meaningless at that level. RedThread resolves **account holders** (card + billing region + days
  since first use) and judges behaviour per holder.
- The closed cases label essentially all fraud from July to October, which made a real fraud model
  trainable. The bank's risk score is right about 37% of the time above 0.85; ours about 92%.
- An **undocumented pattern**: one Samsung device profile, always new to the account and behind an
  anonymous proxy, appears across dozens of unrelated cards. Ring detection isolates it without
  chaining through phones that thousands of people share.
- Holders with a prior confirmed-fraud case have 57% of their later transactions confirmed as fraud,
  against a 1.9% base rate — which is why the agent is told never to explain away a high model score
  as "normal for this holder".

## Does it work?

The benchmark's answer key is hidden, so accuracy is measured by replaying closed cases the bank's
analysts already decided, with point-in-time retrieval (`as_of`) so the agent cannot see its own
outcome or anything that happened later.

**The first version of that test was wrong, and it flattered us badly.** It gave every confirmed case
a customer-report trigger and every cleared case a model-score trigger, so the trigger alone predicted
the answer: an agent could score full marks by reading the alert type and never investigating. That is
where an earlier "24/24 verdicts, Brier 0.005" came from. The trigger is now assigned independently of
the outcome, the flagged transaction's real legacy score is used instead of a flattering constant, and
accuracy is reported **per trigger**, so leaning on the trigger shows up as a gap between the strata.

On the honest test the same pipeline scored **59%**, with a Brier score of **0.36** — worse than
guessing the base rate, because the wrong answers were delivered at 0.97. Two things had been hiding
behind the broken exam.

**The evidence was multiplying itself.** One likelihood ratio per basis, multiplied out, assumes the
bases are independent; device, holder behaviour, region and timing all move together in a real fraud,
so six findings became certainty whatever the truth.

**The customer's reply was a mirror.** The agent asks for evidence when unsure, and since the dataset
has no customers the reply is simulated — but it was chosen from the prior and then scored as
evidence at eight to one. A case weighed at 0.65 produced a denial and came out at 0.94. It could only
amplify, and it destroyed every `uncertain` verdict before it reached the answer.

The aggregate is now tempered, `logit(posterior) = logit(prior) + 0.4 × Σ log LR`, with the factor
fitted on half the cases and reported on the half it never saw (`scripts/fit_aggregation.py`). The
prior for a customer's denial dropped from 0.6 to a neutral 0.5: every customer-report alert in the
closed-case history was confirmed fraud, but that reflects how the bank routed work, and the benchmark
pack is deliberately balanced. And a simulated reply now moves belief only when it carries information
the prior did not already fix — a recurring-charge match, read out of the holder's history rather than
out of the agent's own estimate.

On the same replayed cases, with both corrections in place:

| Replayed closed cases (n=60) | Result |
|---|---|
| Verdict accuracy | **75%** |
| Confirmed fraud caught | 70% |
| Cleared cases left alone | 80% |
| Calibration (Brier) | **0.277** |
| Pattern accuracy on fraud | 70% |
| Affected-transaction recall / precision | 0.79 / 0.92 |
| Agreement with the analysts' filing decision | 75% |

Against the same 60 cases before the corrections, verdict accuracy was 59% and the Brier score 0.357.
What moved most is what a bank would care about most:
**legitimate customers wrongly accused of fraud fell from 17 to 6, and missed fraud from 7 to 3**,
while 17 genuinely ambiguous cases are now left `uncertain` and escalated to an analyst instead of
being forced into a confident answer.

The check that the agent is investigating rather than reading the alert type is the split by trigger.
It used to be lopsided — 54% on customer reports against 67% on model alerts, because a denial was
treated as close to proof. It is now 80% on 35 customer reports and 68% on 25 model alerts: the gap is
gone, which is the result we wanted; the headline accuracy is the side effect.

These cases come from the same generator as the benchmark, and 60 runs carry wide error bars, so
treat the second decimal place as noise.

The pattern classifier is measured separately against every confirmed-fraud closed case
(`python scripts/eval_patterns.py`): **96.2% agreement with the bank's analysts on 4,665 cases**. It
is strong on the four common patterns and genuinely weak on two — card testing (recall 0.062, a rare
pattern easily confused with small legitimate purchases) and undocumented patterns. Both are shown in
the interface rather than hidden.

A note on model selection: `gemini-3.8-flash` with thinking=high was chosen over
`gemini-3.1-pro-preview` on replayed cases, but that comparison ran on the flawed harness described
above, so treat the margin as unverified until it is re-run.

## The interface

A fraud analyst's workbench, not a dashboard. Design notes and the reasoning behind every colour and
type choice are in [`context/design.md`](context/design.md).

| Route | Answers |
|---|---|
| `/` | what is in front of the team, separating the bank's queue from the alerts the agent raised itself |
| `/case/:id` | why this verdict, what is uncertain, what happens next, who signs it off |
| `/missed` | what continuous monitoring adds over the bank's queue |
| `/rings/:id?` | is this one card, or an organised group |
| `/trust` | should you believe it — including where it fails |

**The thread is a scrubber.** Each investigation is a line down the left of the case file, one node
per step. Arrow keys walk it backwards, and the whole case file rewinds with it: the evidence graph
shows only the entities known by then, the belief scale shows where belief stood — with an explicit
"no estimate yet" region, because belief is genuinely known at only three points — the evidence digest
swaps to the tool that ran, and the action plan shows the plan as of then. One control drives five
views.

**Counterfactuals are live.** Because the ledger arithmetic is deterministic, unticking any line
recomputes the probability *and* the recommended action through the same functions the agent used —
no model call, no second implementation to drift.

**Presenter mode.** `/case/:id?replay=1` pushes the stored trace through the same state machine at a
readable pace. It is the real trace, so the demo can be recorded with the workspace suspended and no
API key.

## Repository layout

| Path | What |
|---|---|
| `src/redthread/agent/` | the agent: workflow, MCP client, tools, prompts, simulator, memory |
| `src/redthread/belief.py` | the evidence ledger and its arithmetic |
| `src/redthread/policy.py` | Fraud Policy v1.0 as code |
| `src/redthread/answer.py`, `validate.py` | answer-file schema and dataset checks |
| `src/redthread/api/` | dashboard backend |
| `src/redthread/model/` | fraud model features and score calibration |
| `gsql/` | schema, vector attributes, loading jobs, installed queries |
| `scripts/` | data prep, model training, graph setup, knowledge base, case runner, evaluation |
| `ui/` | the workbench (React, Vite) |
| `cases/` | the 20 answer files |
| `cases_extra/` | alerts the agent raised by itself |
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
python scripts/install_algorithms.py              # TigerGraph GDS: tg_louvain over card-device
python scripts/build_knowledge.py --fetch         # GraphRAG knowledge base
python scripts/export_ui_data.py                  # ring and community views for the interface

python scripts/run_cases.py                       # investigate all 20 cases -> cases/
python -m redthread.validate cases                # check every answer file
python scripts/monitor.py --max-alerts 25         # agent raises its own alerts -> cases_extra/

# measurement
python scripts/backtest.py --n 60 --month 10 --seed 909   # replayed closed cases
python scripts/fit_aggregation.py                 # fit the tempering, dev/held-out split
python scripts/eval_patterns.py                   # pattern classifier vs 4,665 analyst labels

# the workbench
python -m uvicorn redthread.api.app:app --port 8000
cd ui && npm install && npx vite                   # http://localhost:5173
```

`python -m pytest` runs the unit tests: policy engine, belief ledger, answer schema, card-ID
derivation, simulator, tools, and the dashboard API.
