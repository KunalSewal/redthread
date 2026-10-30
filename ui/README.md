# RedThread workbench (UI)

The analyst's workbench for RedThread, an agentic fraud investigator on TigerGraph. It is also what
the judges see in the demo, so every screen has to answer one question for a fraud analyst, show the
IDs behind every claim, and never invent a number the backend did not compute.

This file is the handover for whoever works on the UI. Read the repo's top-level `README.md` section
**The final round** first (ten minutes): it says what the agent does and why each screen exists.

## Run it

**Without data, a graph or keys (mock mode):** the API responses are snapshotted in `ui/mock/api/`.

```bash
cd ui
npm install
npm run dev:mock            # http://localhost:5173, reads ui/mock/api/*.json
```

Mock mode is read-only: approving, challenging or starting an investigation returns a clear 503. The
snapshot is regenerated from the real backend with `python scripts/snapshot_api.py` (repo root). Tell
the backend owner if you need a response the snapshot lacks.

**Against the real backend** (needs the dataset, `runs/` traces, `.env` and the TigerGraph workspace):

```bash
.venv/Scripts/python -m uvicorn redthread.api.app:app --port 8000   # repo root
cd ui && npx vite                                                    # proxies /api to :8000
```

Before you push: `npx tsc --noEmit -p .` and `npm run lint` must pass.

## Routes

| Route | Page | The one question it answers |
|---|---|---|
| `/` | `pages/Docket.tsx` | What is in front of the team? The 18 final-round alerts (`HHF-*`) plus the alerts the agent raised itself in Round 1 (`MON-*`) |
| `/case/:id` | `pages/CaseFile.tsx` | Why this verdict, what is uncertain, what happens next, who signs it off |
| `/audit/:id` | `pages/Audit.tsx` | The regulator's view: what the agent saw at each step, which query, what came back, why the probability moved |
| `/missed` | `pages/Missed.tsx` | What continuous monitoring found that the bank's queue did not (Round 1) |
| `/rings/:id?` | `pages/Rings.tsx` | One card or an organised group? Device rings, Louvain communities, and a containment plan per ring and January scheme |
| `/trust` | `pages/Trust.tsx` | Should you believe it? Drills, attacks, ablation, backtests, data problems, Round 1's replay |

Components: `Thread` (the step-by-step scrubber on the case file), `EvidenceGraph` (d3-force graph of
the entities known by the current step), `BeliefLedger` and `BeliefScale` (how the probability was
built), `EvidenceDigest` (what the tool at the current step returned), `Actions` (the plan, approvals,
and challenges), `Boundary` (error boundary).

## The API

All types are in `src/api.ts`; all calls go through its `api` object.

| Endpoint | Type | Notes |
|---|---|---|
| `GET /api/cases` | `CaseRow[]` | the docket |
| `GET /api/cases/{id}` | `CaseDetail` | answer, trace events, evidence digests, belief ledger, actions with approval state, `handover`, evidence graph |
| `GET /api/cases/{id}/replay` | `Replay` | audit view: steps with query, parameters, what came back, evidence held, probability |
| `GET /api/cases/{id}/handover` | `Handover` | where the case stands: done, waiting (and for which role), contested challenges, next step |
| `GET /api/cases/{id}/challenges` | `ChallengeRecord[]` | evidenced disagreements and their second approvals |
| `POST /api/cases/{id}/approvals` | | approve or reject an L1/L2 action; needs `Authorization: Bearer <approver key>` |
| `POST /api/cases/{id}/challenges` | `ChallengeRecord` | disagree with the verdict: `{position, reason, evidence_ids}`; the server weighs it |
| `POST /api/cases/{id}/challenges/{n}/review` | | a second, different L2 approver upholds or overrules a contested challenge |
| `POST /api/cases/{id}/counterfactual` | | strike ledger lines out and recompute probability and actions |
| `POST /api/cases/{id}/investigate` + `GET .../stream` | SSE | run an investigation live and stream its events |
| `GET /api/rings`, `/api/rings/{id}` | `Rings`, `Ring` | |
| `GET /api/containment` | `Containment` | plans: blocks, exposure cut, customers touched, monitor list |
| `GET /api/evaluation` | `Evaluation` | everything measured, including `final_round` (drills, attacks, ablation, detector backtest, data quality) |
| `GET /api/monitoring`, `/api/overview`, `/api/policy` | | |
| `GET /api/whoami` | | the approver behind a key |

Who approves comes from the key, never from the request body (a body naming a role is refused, 422).
Rejecting a block or report on a fraud verdict needs an accepted or upheld challenge first (409
otherwise): the UI should explain that, not hide the button.

## What the data means (the parts the screens show)

- **An answer** (`answer.case`): `verdict` (fraud, legitimate, uncertain), `fraud_probability`,
  `pattern` (`undocumented` means it fits no documented pattern, with a `pattern_description`),
  `affected_txn_ids`, `connected_card_ids`, `exposure_usd`, `evidence` (each claim with `ref`, the
  query that produced it, and `entity_ids`), `summary`. `next_best_actions` has `initial`, `final` and
  `what_changed`; each action has a `route` (`auto`, `L1`, `L2`).
- **The belief ledger** (`belief.ledger`): one line per finding with `basis`, `direction`, `strength`
  and `lr` (what it multiplied the odds by). `counted: false` lines did not move the probability,
  because another line on the same fact was stronger, or it was already the prior (`as_prior`), or it
  is a model score from a month the model never saw (`uninformative`).
- **The January detectors** (in `evidence`): `activity_shift.run` is the charges the card had never
  made before (the episode), and `scheme_peers` is how many other customers' cards started the same thing
  in the same 30 days, against the same window one and two months earlier (`other_cards_now`,
  `other_cards_month_before`, `other_cards_two_months_before`, `peers`). `recipient_spike` is the same
  comparison for cards paying one recipient email domain. These are the strongest evidence in the
  fraud cases and are barely visualised today.
- **Events** (`events`): kinds include `alert`, `quarantined` (text addressed to the agent, set aside),
  `evidence`, `assessment`, `recommendation`, `case_opened`, `reply`, `report`, `memory`,
  `model_reused`, `model_degraded`, `halted`.

## Design rules (keep them)

- Tokens are in `src/index.css` (`--thread` orange, `--cleared` teal, `--warn`, ink and graphite
  greys) with a light theme. Use tokens, never raw colours.
- **Orange means fraud and nothing else**: never "selected", never a primary button. An uncertain
  verdict gets no hue.
- Copy: sentence case, plain verbs, no all-caps labels, no "·" separators, no "→" on links. A button
  says what happens ("Submit for weighing", "Uphold").
- Every number on screen comes from the API. The UI never computes a verdict, a probability or a
  route. If a number is missing, say so.
- Show the IDs behind claims (transactions, cards, cases); they are what makes a claim checkable.
- Keyboard and focus work everywhere; respect reduced motion; layouts hold at 1280 px and on a laptop.

## Open UI work, in priority order for the demo

1. **Evidence graph on the case file shows the wrong story for the January cases.** For HHF-004 it
   centres on a generic device used by 480 cards, while the case is about 6 small charges the card
   never made and 20 other cards that started the same thing. Show the run and the peer cards (from
   `evidence.activity_shift` and `evidence.scheme_peers`), and stop labels overlapping at the top.
2. **A visual for the scheme finding** on the case file: the run as a small timeline of charges, and
   the peer count now against the two earlier windows (three bars or numbers, not a chart for its own
   sake).
3. **Docket**: separate the 18 final-round cases from Round 1's `MON-*` alerts, with a filter by
   verdict.
4. **Audit view** (`/audit/:id`): left-hand step list you can click, arrow keys, and each evidence ref
   linking to its step.
5. **Containment** (`/rings`): a detail view per plan showing which cards are blocked, which are
   monitored, and who each action touches.
6. **Where it stands** box and **challenge** panel on the case file are functional but plain: give
   them the same care as the rest.
7. A final-round screenshot for the top of the repo README (`assets/`), once the above lands.

## Working together

- Branch from `round2` (for example `ui-polish`) and open a pull request into `round2`.
- Do not change API shapes in `src/api.ts` without telling the backend owner; the backend is the
  source of truth and the README's numbers are filled from the same files.
- The answers and the mock snapshot will be regenerated once more before submission; build against
  the shapes, not specific values.
