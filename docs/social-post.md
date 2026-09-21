# Social post drafts

Written for posting by the project owner. Pick one, attach the demo video or a screenshot of a case
with its evidence graph, and link the blog post. **Both versions tag @TigerGraphDB**, which the
submission requires — check the handle survives your editing.

## LinkedIn

I built an agentic fraud investigator on @TigerGraphDB for the Hacker House Goa challenge: 590,000
card transactions, no fraud labels, and twenty alerts to decide on. The most useful thing I learned
was not about the agent.

**We built our own exam, scored 24 out of 24, and the exam was rigged.** The benchmark's answer key
is hidden, so we tested the agent by replaying closed cases the bank's analysts had already decided.
It scored perfectly. Then I read my own test harness and found this:

    "trigger_type": "customer_report" if confirmed else "risk_score"

Every confirmed fraud arrived as a customer complaint and every cleared case as a model alert. The
alert type *was* the answer. An agent that ignored the graph entirely would also have scored 24 out
of 24. On an honest version of the test, the same pipeline scored 59%.

Two real defects had been hiding behind that score. The evidence was multiplying itself — one
likelihood ratio per signal, compounded, assumes the signals are independent, and the device, the
holder's behaviour, the region and the timing all move together in a real fraud, so six findings
became certainty regardless of truth. And the simulated customer reply was chosen from the agent's
own prior and then scored as evidence against it, which could only amplify what it already believed.

Fixing both: verdict accuracy 59% → 75%, and legitimate customers wrongly accused of fraud fell from
17 to 6. The part I care about most is that the agent now says "uncertain" on 17 of 60 cases and
escalates them to a human, instead of committing confidently to a coin flip.

Two other things surprised me. The "customers" in this data aren't people — each ID is a card-issuer
bucket of many unrelated cardholders, and recovering the individual behind each transaction turned
13,553 buckets into 222,481 real account holders. And a graph sees what a per-transaction model
cannot: on one case our model scored the flagged transaction 0.0065, invisible, while the graph showed
twenty-one cards using that same phone that month, each with the device new to the account and behind
a proxy.

If you build one of these, write the test that can fail.

Write-up: [link] · Code: https://github.com/KunalSewal/redthread

## X

Built an agentic fraud investigator on @TigerGraphDB. 590k transactions, no labels, 20 alerts.

It scored 24/24 on the exam we built for it. Then I read the harness:

    "trigger_type": "customer_report" if confirmed else "risk_score"

The alert type WAS the answer. An agent ignoring the graph scores 24/24 too. On an honest test: 59%.

Two defects were hiding behind that. Evidence multiplying itself — six correlated findings compound
into certainty. And the simulated customer reply was picked from the agent's own prior, then scored
as evidence against it. A mirror, not a witness.

Fixed: 59% → 75%, and legitimate customers wrongly accused fell 17 → 6. It now answers "uncertain"
on 17 of 60 cases and escalates them, instead of confidently guessing.

Write the test that can fail.

[blog link] · github.com/KunalSewal/redthread
