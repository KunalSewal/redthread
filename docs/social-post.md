# Social post drafts

Written for posting by the project owner. Pick one, attach the demo video or a screenshot of a case
with its evidence graph, and link the blog post.

## LinkedIn

I spent the weekend building a fraud investigator on @TigerGraph for the Hacker House Goa challenge:
590,000 card transactions, no fraud labels, and twenty alerts to decide on. Three things surprised
me.

The "customers" in the data aren't people. Each ID is a card-issuer bucket holding many unrelated
cardholders, so "unusual for this customer" is meaningless: one has 422 transactions across forty
regions. A column counting days since the card's first use lets you recover the individual behind
each transaction, which turns 13,553 buckets into 222,481 real account holders. Every behavioural
question only became answerable after that.

A graph sees things a per-transaction model cannot. On one case our fraud model scored the flagged
transaction 0.0065 — invisible. In the graph, twenty-one different cards had used that same phone
that month, each with the device new to the account and behind a proxy. That is a pattern whose
entire signature lives *across* accounts.

The best fix was to stop asking the LLM. It named fraud patterns correctly about one time in eight.
But those patterns are mechanical: mixed channel in one episode is account takeover in 230 of 230
closed cases. Twenty lines of code agree with the bank's analysts on 96% of 4,665 cases. The model
decides which transactions belong to the episode; the code names the pattern; the policy engine
picks the action and the approval route.

Write-up: [link] · Code: https://github.com/KunalSewal/redthread

## X

Built a fraud investigator on @TigerGraphDB this weekend. 590k transactions, no labels, 20 alerts.

The "customers" aren't people — each ID is an issuer bucket of many cardholders. Recovering the real
holder (card + region + days since first use) turned 13,553 buckets into 222,481 people, and made
every behavioural signal mean something.

One case: our model scored the flagged transaction 0.0065. The graph showed 21 cards using the same
phone that month, all new to the account, all behind a proxy. A model per transaction cannot see a
pattern that lives across accounts.

Best decision: stop asking the LLM to name the pattern. It got it right 1 time in 8. The patterns
are mechanical — 20 lines of code match the bank's analysts on 96% of 4,665 closed cases.

[blog link] · github.com/KunalSewal/redthread
