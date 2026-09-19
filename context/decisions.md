# Decision Log

Record architecture decisions here as they are made: date, decision, why, alternatives rejected.
Open questions stay at the top until resolved.

## Open questions

(none)

## Decided

- **2026-09-19: This is the HHGOA shortlisting task; code is written now.** The "code during the
  event" rule applies to the Oct 28–31 event itself, not to this task.
- **2026-09-19: TigerGraph Savanna free tier (TG-4), not local Community Edition.** The dev machine
  has 15.7 GB RAM total (CE needs 16 GB minimum, 20–24 GB recommended for this data). Savanna gives
  256 GB with no ops. Cost: auto-stop and credit clock; pre-warm before demos.
- **2026-09-19: Claude (Anthropic API) as the LLM, LangGraph as the orchestrator, official
  `tigergraph-mcp` via `langchain-mcp-adapters` as the tool surface.** LangGraph is the MCP server's
  recommended client and gives explicit, inspectable state for case progression.
- **2026-09-19: Local embeddings (`BAAI/bge-small-en-v1.5`, 384-d) for GraphRAG.** Free,
  reproducible, no second API key; well under the 4096-d vector cap.
- **2026-09-19: UI = FastAPI + React (Vite).** Keeps the backend in the same Python package as the agent.
- **2026-09-19: Repo `github.com/KunalSewal/redthread` (public).** Personal reference notes
  (`Guide.md`, the briefing, the problem-statement docx) stay local and git-ignored.

- **2026-09-19: Card IDs are derived, not loaded.** `card_id = customer_id + "-K" + rank(str(card6))`
  within the customer. Verified 100% against all labeled transactions. See `context/data-dictionary.md`.
- **2026-09-19: Policy logic is deterministic code.** Action routes, exposure, SAR/route consistency,
  and ID validation are Python, not LLM output. The LLM proposes verdict/pattern/probability with evidence;
  the policy engine turns that into actions and routes. Reason: zero-score risks on exact identifiers.
- **2026-09-19: Large CSVs stay out of git and out of the model's context.** `.gitignore` +
  `.claude/settings.json` deny rules; profiling is done through pandas aggregates.
