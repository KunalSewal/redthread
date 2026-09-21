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

## The fourth time, the thing that was confidently wrong was us

Those three we caught by reading the agent's output. The fourth we caught by doubting our own exam,
and it was worse than all of them.

The benchmark's answer key is hidden, so we built our own test: replay closed cases the bank's
analysts already decided, with point-in-time retrieval so the agent cannot see its own outcome or
anything later. It scored **24 out of 24**, with a Brier score of 0.005. We wrote that number in the
README.

It was meaningless. Rebuilding each alert, we had set the trigger from the outcome:

```python
"trigger_type": "customer_report" if confirmed else "risk_score",
```

Every confirmed fraud arrived as a customer complaint and every cleared case as a model alert. The
alert type *was* the answer. An agent that ignored the graph entirely and pattern-matched the first
line of the prompt would also have scored 24 out of 24. We had built a test that could not fail, and
then we had passed it.

The fix is three lines: assign the trigger independently of the outcome, use the flagged
transaction's real legacy score instead of a flattering constant, and report accuracy **per trigger**
so that leaning on the trigger shows up as a gap between the strata. On the honest version, the same
pipeline scored **59%**, with a Brier score of **0.36** — worse than guessing the base rate, because
the wrong answers were delivered at 0.97.

Two things had been hiding behind that broken exam.

**The evidence was multiplying itself.** Our agent does not state a probability. It judges each
finding — which way it points, how strong it is, and what it rests on — and the code does the Bayes,
one likelihood ratio per independent basis. But the bases are not independent. In a real fraud the
device, the holder's behaviour, the region and the timing all move together, so six findings pointing
one way multiply into certainty the evidence cannot support. Across the twenty benchmark cases,
*every* legitimate case sat at 0.03 and *every* fraud case at 0.88 or above, with nothing in between.
The verdict tracked the trigger: fraud on 8 of 8 customer complaints, legitimate on 9 of 11 model
alerts.

The correction is standard for correlated evidence — temper the sum before it becomes a probability:

```
logit(posterior) = logit(prior) + 0.4 × Σ log LR
```

We fitted that 0.4 on half the backtest cases and reported it on the half it never saw, optimising
not accuracy but an operational cost, because for a bank the mistakes are not symmetric: an
`uncertain` verdict is escalated to an analyst and the case still gets handled, while a blocked
legitimate customer and a missed fraud are both real damage. Optimising calibration alone drove fraud
recall to 0.29 by pushing everything to the middle, which is a different failure, not a fix.

**The customer's reply was a mirror.** The agent asks for more evidence when it is unsure. The
dataset has no customers, so we simulate the reply — and we chose it from the prior:

```python
denies = prior >= 0.5 and not recurring
```

Then we updated that same prior with a likelihood ratio of eight. A case weighed at 0.65 produced a
denial and came out at 0.94; one at 0.38 produced a confirmation and came out at 0.07. It was
circular, it could only amplify, and it destroyed every `uncertain` verdict before it reached the
answer — which is why the agent, in months of runs, had never once returned one. On 59 replayed cases
it touched thirteen and got ten of them wrong.

A reply you inferred from your own belief is not evidence about that belief. It now moves the
probability only when it carries information the prior did not already fix — a charge matching the
holder's own recurring pattern, which is read out of the transaction history rather than out of the
agent's head — and an assumed reply no longer counts as an independent signal in the policy's
stopping rule.

## Does it work?

So we rebuilt the exam and ran it again. On the same 60 replayed cases, with the trigger
independent of the outcome:

| Replayed closed cases (n=60) | Before | After |
|---|---|---|
| Verdict accuracy | 59% | **75%** |
| Cleared cases left alone | 41% | **80%** |
| Confirmed fraud caught | 77% | 70% |
| Calibration (Brier) | 0.357 | **0.277** |
| Legitimate customers accused of fraud | 17 | **6** |
| Fraud closed as legitimate | 7 | **3** |
| Left `uncertain` for an analyst | 0 | **17** |

The number we care about most is the third from the bottom. Six wrongly accused customers is still
six too many, but it is a third of what the confident version produced, and the cases it now hesitates
on are escalated rather than decided.

The honest way to check whether an agent is investigating or just reading the alert type is to split
the score by trigger. Ours used to be lopsided — 54% on customer complaints against 67% on model
alerts, because it had learned that a denial was close to proof. It is now 80% and 68%. The gap is
gone, which is the result we actually wanted; the headline accuracy is the side effect.

None of this is a good score in absolute terms. Three quarters of verdicts right, on a test where half
the cases are legitimate, is a system worth putting in front of an analyst, not one worth letting run
unattended — and that is exactly what the policy engine does with it.

The pattern classifier is measured separately against every confirmed-fraud closed case: **96.2%
agreement with the bank's analysts on 4,665 cases**. It is strong on the four common patterns and
genuinely weak on two — card testing (recall 0.062) and undocumented patterns — and the interface
shows both rather than hiding them.

It also runs unprompted. Pointed at November and December with no alerts at all, it raised 25 cases
of its own — 13 from ring devices, 12 from transactions our model scored high while the bank's legacy
score stayed low. It called fraud in 14 of them, worth $3,900 of exposure, filed 13 reports, and left
the other 11 `uncertain` for a human rather than guessing. The bank had scored 19 of the 25 below
0.30. Three were charges of $149.99, $150.09 and $150.04 on different cards through the same devices:
a per-transaction model sees three ordinary purchases, and the graph sees one operator.

## The workbench

The interface is built around a single idea: **the thread is a scrubber.** Each investigation is a
line down the left of the case file, one node per step. Arrow keys walk it backwards, and the whole
case file rewinds with it — the evidence graph shows only the entities known by then, the belief
scale shows where belief stood, the evidence digest swaps to the tool that ran, and the action plan
shows the plan as of then. One control drives five views, which means the story can be told in one
continuous move instead of a tour of tabs.

Two details matter more than they look. The belief scale draws an explicit **"no estimate yet"**
region, because belief is genuinely known at only three points and drawing a smooth curve between
them would be inventing data. And because the ledger arithmetic is deterministic, **any line can be
struck out** and the probability *and the recommended action* recompute live, through the same
functions the agent used — explainability with no model call and nothing to drift.

Orange means fraud, and nothing else: not "selected", not "primary button", not "a series in a
chart". If everything can be orange, orange says nothing. Uncertain gets no hue at all.

## Choosing the model by measuring it

Replaying closed cases, Gemini 3.8 Flash with thinking turned up beat Pro 3.1 — 26 right against 23,
with better calibration and no cleared customer accused of fraud, where Pro produced two at 0.95 or
above. The newer, cheaper, faster generation simply reasoned better about this evidence.

That comparison ran on the flawed harness described above, so we are reporting it as unverified
rather than quietly leaving it in the results table. It is the honest consequence of finding a broken
exam: everything measured with it has to be re-earned.

## What we would do with more time

- **Card testing** is detected by the policy's R5 sequence, but the labelled card-testing episodes in
  the closed cases list only the fraudulent transactions, so the classifier recognises 1 in 16.
- **The customer simulator is still a single rule.** Now that it is honest about carrying no
  information, the next step is to make it genuinely informative — reply latency, partial recall, and
  rule R4's no-reply-within-24-hours path, which our agent still never hits.
- **The model judges its own evidence strength**, and it is generous: across the backtest it called
  84 findings "strong" and 19 "decisive". Tempering corrects the aggregate, but calibrating the
  strength labels themselves against outcomes would be better than correcting them afterwards.
- **Monitoring is a batch script.** The pieces are there for it to run continuously against the
  risk-score stream instead.

## Stack

TigerGraph Savanna (free tier, TG-00) · GSQL with 21 installed queries, connected-components ring
detection and the GDS library's `tg_louvain` for communities · TigerVector for GraphRAG · the
official `tigergraph-mcp` server · LangGraph · Gemini · LightGBM · FastAPI and React.

Code: https://github.com/KunalSewal/redthread
