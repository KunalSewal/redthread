# Decision Log

Record architecture decisions here as they are made: date, decision, why, alternatives rejected.
Open questions stay at the top until resolved.

## Open questions

(none)

## Decided

- **2026-09-20: `gemini-3.8-flash` (thinking=high) as the reasoning model, chosen by backtest.**
  It beat `gemini-3.1-pro-preview` 26/28 vs 23/28 on replayed closed cases, with far better
  calibration and no cleared case called fraud (Pro produced two at p>=0.95). Pro's thinking level
  made no difference. Evidence in `runs/confirm_*.json`; rationale recorded in `src/redthread/config.py`.
- **2026-09-20: the fraud pattern is derived from the episode, not judged by the LLM.**
  96.2% agreement with analysts across 4,665 confirmed-fraud closed cases vs ~13% for the LLM
  (`scripts/eval_patterns.py`). The LLM still decides which transactions form the episode.
- **2026-09-20: point-in-time retrieval everywhere (`as_of`).** An investigation never sees cases
  opened at or after its alert. Required for honest backtesting and stops a rerun feeding a later
  case's memory into an earlier alert.
- **2026-09-20: R10 inputs (cards with fraud, credentials compromised) are computed from the
  episode.** The LLM counted unrelated history in the issuer bucket and twice recommended blocking
  every card a customer held; analysts never did that once in 5,565 closed cases.

- **2026-09-19: This is the HHGOA shortlisting task; code is written now.** The "code during the
  event" rule applies to the Oct 28–31 event itself, not to this task.
- **2026-09-19: TigerGraph Savanna free tier (TG-4), not local Community Edition.** The dev machine
  has 15.7 GB RAM total (CE needs 16 GB minimum, 20–24 GB recommended for this data). Savanna gives
  256 GB with no ops. Cost: auto-stop and credit clock; pre-warm before demos.
- **2026-09-19: LangGraph as the orchestrator, official `tigergraph-mcp` as the tool surface.**
  LangGraph is the MCP server's recommended client and gives explicit, inspectable state for case
  progression. The agent's MCP server runs with a `TG_ALLOWED_TOOLS` allowlist (read-only tools plus
  the case write-back query).
- **2026-09-20: Google Gemini as the LLM (supersedes Claude).** The owner has a Gemini API key.
  `gemini-3.1-pro-preview` for investigation reasoning, `gemini-3.8-flash` for light tasks; both
  pinned in `src/redthread/config.py` and overridable by env var. Verified callable on 2026-09-20.
- **2026-09-19: Local embeddings (`BAAI/bge-small-en-v1.5`, 384-d) for GraphRAG.** Free,
  reproducible, no second API key; well under the 4096-d vector cap.
- **2026-09-19: UI = FastAPI + React (Vite).** Keeps the backend in the same Python package as the agent.
- **2026-09-19: Train our own transaction fraud model on the closed cases.** The closed cases label
  essentially all Jul–Oct fraud, so a LightGBM model is trainable and far better than the bank's
  score (AP 0.64 vs 0.25 on an October holdout). It is one evidence signal the agent cites, not the
  verdict; the agent still has to establish pattern, episode, links and policy actions from the graph.
  Only the provided dataset is used (never the public IEEE-CIS files).
- **2026-09-19: Model resolved account holders as a `Holder` vertex.** `customer_id` is an issuer
  bucket; `card + region + (day - D1)` recovers the individual. Without this, "cardholder history"
  is the history of a crowd.
- **2026-09-19: No reliance on data-generation artifacts.** Signals must be ones a fraud analyst
  could defend (behaviour, devices, links, prior cases, model scores), not quirks of how the
  benchmark was built.
- **2026-09-19: Repo `github.com/KunalSewal/redthread` (public).** Personal reference notes
  (`Guide.md`, the briefing, the problem-statement docx) stay local and git-ignored.

- **2026-09-19: Card IDs are derived, not loaded.** `card_id = customer_id + "-K" + rank(str(card6))`
  within the customer. Verified 100% against all labeled transactions. See `context/data-dictionary.md`.
- **2026-09-19: Policy logic is deterministic code.** Action routes, exposure, SAR/route consistency,
  and ID validation are Python, not LLM output. The LLM proposes verdict/pattern/probability with evidence;
  the policy engine turns that into actions and routes. Reason: zero-score risks on exact identifiers.
- **2026-09-19: Large CSVs stay out of git and out of the model's context.** `.gitignore` +
  `.claude/settings.json` deny rules; profiling is done through pandas aggregates.
- **2026-09-20: Louvain communities complement ring detection, as weak evidence only.** TigerGraph's
  GDS `tg_louvain` runs over the card-device projection weighted by transaction count, and the new
  `community_profile` query is exposed to the agent as the `community` tool. It fires when the card's
  device has no ring, which is 19 of the 20 benchmark cases, so it is what gives most cases any
  cross-card evidence at all. Strength was measured, not assumed: on 500 closed cases a community
  fraud-rate lift above 5x occurs in 30% of confirmed fraud and 16% of cleared cases, a likelihood
  ratio of 1.9 (2.5 for a lift of 2-5x). An earlier measurement looked far stronger (median lift 5.6x
  vs 0x) only because it silently dropped single-card communities, which are 40% of cards and almost
  always benign. The prompt therefore caps this evidence at "weak" and records a zero-fraud community
  as mildly exculpatory. Artefact: `data/processed/community_lift_lr.json`.
- **2026-09-20: Independence is judged per entity, not only per declared basis.** The belief ledger
  already counted one item per basis, but the model can file three findings about one device under
  `device`, `cross_card_links` and `prior_cases`, compounding 8x8x8 for what is a single fact. Counted
  findings that rest on an entity a stronger finding already used now carry half their weight in
  log-odds. The card, holder and transaction under investigation are excluded, since they appear in
  nearly every claim by construction and would otherwise damp everything. Entity IDs are parsed out of
  the claim text as well as `entity_ids`, because the model names the device in prose but routinely
  omits it from the ID list.
- **2026-09-20: The graded answer file carries exactly the four evidence fields data/README.md
  specifies.** `direction`, `strength` and `basis` drive the ledger and live in the trace and the UI;
  emitting them in `cases/*.json` would deviate from the published contract, and missing or malformed
  fields score zero.
- **2026-09-20: The old backtest measured the trigger, not the investigation.** `build_alerts` gave
  every confirmed case a `customer_report` trigger and every cleared case a `risk_score` one, so the
  trigger alone predicted the outcome and an agent could score full marks without investigating.
  That is where "24/24 verdicts, Brier 0.005" came from, and it is why that number must never be
  quoted again. The trigger is now assigned independently of the outcome, the flagged transaction's
  real legacy score is used instead of a flattering constant, and accuracy is reported per trigger so
  that leaning on the trigger would show up as a gap between the two strata. On the honest test the
  same pipeline scored 61.7% with a Brier of 0.36 — worse than guessing the base rate, because the
  wrong answers were given at 0.97.
- **2026-09-20: The evidence ledger multiplied correlated evidence into false certainty.** One
  likelihood ratio per basis, multiplied out, assumes the bases are independent; device, holder
  behaviour, region and timing all move together in a real fraud, so six findings became a
  probability of 0.97 whatever the truth. On the benchmark this showed up as verdicts that tracked
  the trigger: fraud on 8 of 8 customer reports, legitimate on 9 of 11 model alerts. The aggregate is
  now tempered, `logit(posterior) = logit(prior) + 0.4 * sum(log LR)`, with 0.4 fitted on half of a
  60-case backtest and reported on the other half (`scripts/fit_aggregation.py`).
- **2026-09-20: A customer's denial opens a case; it does not decide it.** The prior for a
  customer-report trigger drops from 0.6 to 0.5. Every such alert in the closed-case history was
  confirmed fraud, but that reflects how the bank routed work, and both the dataset README and the
  briefing warn that the benchmark pack is deliberately balanced. Fitting the prior freely gave 0.25,
  which scores better still on the backtest but is tuned to a trigger mix we invented by coin flip,
  so the neutral 0.5 was taken instead. Measured on the held-out half, tempering plus the neutral
  prior cut missed fraud from 3 to 1 and cleared customers wrongly accused of fraud from 10 to 6,
  and moved Brier from 0.405 to 0.332. The cost of the trade is hesitation rather than error: the
  fraud cases it no longer calls outright become `uncertain`, which policy escalates to an analyst.
- **2026-09-20: Accuracy alone is the wrong objective for this agent, so the fit optimises cost.**
  An `uncertain` verdict is not a wrong answer — policy escalates it and asks the customer — while a
  confident flip in either direction is real damage. `scripts/fit_aggregation.py` therefore scores a
  blocked legitimate customer and a missed fraud at 1.0, an escalated fraud at 0.3 and an escalated
  cleared case at 0.2, and reports Brier alongside. Optimising Brier alone drove fraud recall to 0.29
  by pushing everything to the middle, which is a different failure, not a fix.
- **2026-09-21: A simulated reply cannot be evidence about the belief that produced it.** The
  evidence-request step chose the customer's reply from the prior (`denies = prior >= 0.5`) and then
  updated that same prior with a likelihood ratio of 8. The loop was circular and could only amplify:
  a case weighed at 0.65 produced a denial and came out at 0.94, one at 0.38 produced a confirmation
  and came out at 0.07. It destroyed every `uncertain` verdict before it reached the answer — which is
  why the agent had never once returned one — and on a 59-case backtest it was wrong in 10 of the 13
  cases it touched. The reply now moves belief only when it carries information the prior did not
  already fix; the one case that qualifies is a recurring-charge match, which is read out of the
  holder's transaction history rather than out of the agent's belief. An assumed reply also no longer
  increments `independent_evidence`, which policy reads for R1 and the stopping rule. Replaying the
  same 59 cases without the circular update: verdict accuracy 0.593 to 0.661, Brier 0.357 to 0.305,
  missed fraud 7 to 3, cleared customers wrongly accused 17 to 11, and 13 cases correctly left
  uncertain for an analyst.
- **2026-09-21: Compare settings on the same cases.** The first "after" backtest used a different
  seed from the "before" run, so it compared two different samples and appeared to show no
  improvement. Because every run stores its belief ledger, the arithmetic can be replayed under other
  settings on identical cases, which is both free and exact. Any future comparison of aggregation
  settings should do that, and any end-to-end comparison should reuse the seed.
