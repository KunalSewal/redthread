# RedThread: teaching an agent to investigate card fraud on TigerGraph

The brief for the TigerGraph challenge at Hacker House Goa was deceptively simple: given a fraud
alert, investigate it and decide what the bank should do. Twenty benchmark cases, an answer key we
never see, and a dataset with no fraud labels in it at all. Half the alerts are legitimate. An agent
that blocks everything fails; so does one that closes everything.

This is what we built, what the data turned out to be hiding, and the three times the agent was
confidently wrong before we caught it.

## The shape of the problem

The dataset is the IEEE-CIS fraud data (590,742 card transactions over six months) with the fraud
flag stripped out. In its place: a risk score from "the bank's model", 5,565 closed investigations
from July to October, a fraud policy with ten rules, and twenty November–December alerts to answer.

The policy is the interesting part. It doesn't ask for a fraud score. It asks for a decision: block
this card (and who must approve that), ask the customer, open a case, file a suspicious activity
report, escalate, or close. It also asks the agent to know when it doesn't know enough yet, and to
change its recommendation when new evidence arrives.

## Finding the people hidden inside the "customers"

The first thing we checked was what a customer looks like. Customer `C12382` has 422 transactions
across more than forty billing regions. So does everyone else, roughly. No human shops like that.

`customer_id` is derived from the card issuer field, so each "customer" is a bucket holding many
unrelated people. Every behavioural signal you would reach for — a new region, an unusual amount,
an unfamiliar product — fires constantly at that level and means nothing.

The IEEE data has a column, `D1`, that counts days since the card was first used. That makes
`day − D1` a constant for one real cardholder. Combine it with the card and billing region and you
recover the individual:

```
holder = card_id | billing region | (day − D1)
```

590,742 transactions resolve into 222,481 account holders. Suddenly "normal for this cardholder"
means something. HHG-001's flagged $77.07 purchase, scored 0.61 by the bank, turns out to be the
same person's weekly $77 purchase in the same region. It's a subscription, not a fraud.

We made `Holder` a vertex. Entity resolution, done in the graph, is what makes every later
behavioural question answerable.

## The bank's model is beatable, and the closed cases say how

Every transaction carries a risk score, and the README warns you not to trust it. It's right: above
0.85, only 37% of those transactions turned out to be fraud.

But the closed cases cover July to October, and their confirmed-fraud transactions amount to 3.37%
of all transactions in those months — almost exactly the fraud rate of the original dataset. In
other words, the closed cases label essentially *all* the fraud in four months. That's a training
set.

A LightGBM model on the original Vesta features plus holder-level aggregates, trained on July to
September and tested on October:

| October holdout | Our model | Bank's risk score |
|---|---|---|
| AUC | **0.968** | 0.866 |
| Average precision | **0.64** | 0.25 |

Scores go into the graph as an attribute on every transaction, with a calibration table beside them,
so the agent reads "0.62" as "about 65% of past transactions scoring like this were fraud" rather
than as a probability it invented. It is evidence, never a verdict.

## What the model cannot see

Case HHG-014 is an analyst asking: several cards this month show purchases from the same unusual
device. Our model scores the flagged transaction **0.0065**. Nothing to see.

The graph disagrees. That transaction came from a Samsung device behind an anonymous proxy, and in
the same month **21 different cards** used that same device profile, every one of them with the
device newly attached to the account. Four closed cases from August and September name the same
device, all confirmed fraud, and all labelled `undocumented` by the bank's own analysts.

This is the case for graph analytics in one picture: a per-transaction model cannot see a pattern
whose entire signature is *shared across accounts*.

Finding rings needs care, though. Our first attempt linked cards through any shared device and
produced a 118-card blob: popular phones (one Galaxy S8 profile is shared by 90 unrelated cards) act
as hubs and chain unrelated fraud together. The definition that works links two cards only through a
**specific** device profile used in a **suspicious** transaction where the device was **new to that
account** — an unfamiliar device turning up on several accounts at once. That yields 9 tight rings,
the largest 7 cards, computed by connected components in GSQL in half a second.

## Architecture

```
alert ─► core evidence (fixed checklist) ─► follow-ups chosen by the LLM ─► assessment
      ─► policy engine: initial actions ─► evidence request ─► simulated reply (Bayesian update)
      ─► policy engine: final actions ─► report + SAR ─► case written back to the graph
```

Choices worth explaining:

**The agent reaches TigerGraph only through the official MCP server**, started with an allowlist so
it sees installed queries and vector search and nothing that can drop a graph. Writes go through
three dedicated queries. Least privilege, enforced by the server rather than by asking nicely in a
prompt.

**A fixed evidence checklist runs before the LLM chooses anything.** Alert context, card window,
holder baseline, device neighbourhood, shared-origin lift, linked cases, similar cases. Every case
gets the same floor of evidence; the LLM's judgement adds to it rather than deciding whether to
bother.

**GraphRAG is retrieval then traversal.** Each policy rule, each fraud pattern, the FinCEN/FFIEC/FATF
guidance and all 5,565 closed-case narratives are embedded into TigerGraph's vector store. A search
for "several cards, same device, anonymous proxy" returns pattern 3, rule R6 and a FATF passage, and
the same query walks from the matching closed cases out to the devices and cards they touched.

**The policy is code, not prompt.** Rules R1–R10, approval routes, SAR criteria and the stopping
rule are ordinary Python with unit tests. The LLM never picks an approval route, never sums an
exposure, and never decides whether a report is required. It establishes facts; the policy engine
turns facts into actions. Every action carries the rule it came from.

**Evidence requests are honest about being simulated.** The dataset provides no customer replies, so
the agent assumes the reply most consistent with the evidence *before* it asked, states that
assumption in the answer, and updates the probability with a stated likelihood ratio. A denial
multiplies the odds by 8. You can check the arithmetic.

**Point-in-time retrieval.** Every retrieval query takes an `as_of`, and cases opened after the
alert stay invisible. It keeps the agent honest in production and makes backtesting meaningful.

## Three times the agent was confidently wrong

**It explained away the strongest signal it had.** On HHG-007 the model scored 0.943 and the agent
concluded *legitimate*, reasoning that the transaction matched the holder's normal behaviour. But
that holder's own history is confirmed fraud. We checked the data: holders with confirmed fraud in
July–September had **57% of their October transactions confirmed as fraud**, against 1.9% for
everyone else. When a holder identity is compromised, "consistent with their baseline" is evidence
*for* fraud. The measured statistic went into the agent's briefing, and the tool now reports the
holder's own fraud history. HHG-007 is now fraud, account takeover, with a ring link.

**It blocked every card a customer had, twice.** Rule R10 permits that only when two of the
customer's cards show confirmed fraud or credentials are confirmed compromised. The LLM counted
historical cases across the issuer bucket — hundreds of unrelated people — and inferred "credentials
compromised" from a pattern guess. In 5,565 closed cases, analysts never once blocked all cards.
Both R10 inputs are now computed from the episode itself, and the action effectively cannot fire
without two of that customer's own cards in the fraud.

**It named the pattern almost randomly.** On a backtest it got the pattern right 12.5% of the time,
calling out-of-region use "account takeover" and account takeover "undocumented". But the five
documented patterns are *mechanical*: mixed channel in one episode is account takeover (230 of 230
closed cases); in-person away from the card's home region is out-of-region use (97% versus 5%);
online with a device new to the account is card-not-present-with-new-device (100% versus 0%). So we
stopped asking. A twenty-line classifier agrees with the bank's analysts on **96.2% of all 4,665
confirmed-fraud cases**. The LLM decides which transactions form the episode; the code names it.

The pattern generalises: when a judgement is really a mechanical property of the evidence, measure
it against the labelled history and write the rule.

## Does it work?

The answer key is hidden, so we built our own exam: replay closed October cases as fresh alerts with
`as_of` set to the moment they opened, so the agent cannot see its own answer, and compare with what
the analysts concluded.

| Replayed October cases (n=24) | Result |
|---|---|
| Verdict accuracy | **24 / 24** |
| Cleared cases correctly cleared | 12 / 12 |
| Confirmed fraud caught | 12 / 12 |
| Pattern accuracy | 83% |
| Affected-transaction recall / precision | 0.90 / 0.90 |
| Calibration (Brier) | 0.005 |
| Agreement with the analysts' filing decision | 71% |

Turning the model's thinking level up changed none of this (identical verdicts and patterns, Brier
0.0051 against 0.0054) while costing about three times the tokens — worth knowing before paying for
deliberation you cannot measure.

Two caveats worth stating. These cases come from the same generator as the benchmark but are not the
benchmark, and the agent had already been improved using *other* closed cases, so this is not a clean
held-out set in the strict sense. And a run of 24 has wide error bars: 24/24 does not mean the next
24 would be perfect.

On the twenty benchmark cases the agent returned 11 fraud and 9 legitimate, filed 5 reports, escalated
1, and asked for extra evidence on 2 — about 84 seconds and 14 graph calls per case.

It also runs unprompted. Pointed at November and December with no alerts at all, it raised six of its
own — three from ring devices, three from transactions our model scored high while the bank's legacy
score stayed low — and found fraud in all six. Three of them were charges of $149.99, $150.09 and
$150.04 on different cards through the same devices. A per-transaction model sees three ordinary
purchases; the graph sees one operator.

## The dashboard

The interface is built around uncertainty rather than a verdict badge. The probability sits on the
policy's own scale, with the thresholds that actually change what the bank may do (0.15 close, 0.30
open a case, 0.70 block on a single signal, 0.85 decisive) marked on it, and an arrow from the
initial estimate to the final one so you can see what the evidence request changed. Below it, the
thread: every graph query, judgement and decision in order. Beside it, the evidence graph, and the
approvals queue, where an L1 team lead can approve a card block but only an L2 fraud manager can
approve a filing — the agent executes only what the policy lets it execute.

## Choosing the model by measuring it

The obvious choice was the Pro tier. The backtest disagreed. Replaying 28 closed cases, Gemini 3.8
Flash with thinking turned up got 26 right against Pro 3.1's 23, with far better calibration (Brier
0.005 against 0.117) and — the part that matters for a bank — no cleared customer accused of fraud,
where Pro produced two at probability 0.95 or above. Raising Pro's thinking level changed nothing.
The newer, cheaper, faster generation simply reasoned better about this evidence, and we would not
have known without an exam we could run ourselves.

## What we would do with more time

- **Card testing** is detected by the policy's R5 sequence, but the labelled card-testing episodes
  in the closed cases list only the fraudulent transactions, so the classifier recognises 1 in 16.
- **The customer simulator is a single rule.** A stronger design would model reply latency and
  partial recall, and would exercise rule R4 (no reply within 24 hours), which our agent never hits.
- **Uncertainty is underused.** `uncertain` is a valid verdict that earns full credit on cases
  designed to be ambiguous, and our agent almost always commits.
- **Monitoring is a batch script.** The pieces are there for it to run continuously against the
  risk-score stream instead.

## Stack

TigerGraph Savanna (free tier, TG-00) · GSQL with 19 installed queries and connected-components ring
detection · TigerVector for GraphRAG · the official `tigergraph-mcp` server · LangGraph · Gemini ·
LightGBM · FastAPI and React.

Code: https://github.com/KunalSewal/redthread
