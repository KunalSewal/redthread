# Build Plan — RedThread

Project name: **RedThread** (repo `github.com/KunalSewal/redthread`). Python package `redthread`.
Tick items as they land. Keep this file current; it is the source of truth for "what next".

## Architecture

```
case_pack / live alert
        │
        ▼
 ┌──────────────── LangGraph investigation graph (src/redthread/agent) ────────────────┐
 │ intake → gather (LLM tool loop) → assess → policy(initial) → request evidence        │
 │        → simulate response → reassess → policy(final) → SAR writer → write-back      │
 └───────┬──────────────────────────────┬─────────────────────────────┬────────────────┘
         │ MCP (stdio, allowlisted)     │ deterministic Python         │ Claude API
         ▼                              ▼                              ▼
 tigergraph-mcp ──► TigerGraph Savanna   policy engine, exposure,      reasoning, tool choice,
   installed GSQL queries,               routes, ID validation,        synthesis, SAR narrative
   vectorSearch (GraphRAG),              answer schema
   graph algorithms (WCC, Jaccard)
         ▲
         │ scripts/prepare_data.py → scripts/load_graph.py → scripts/install_queries.py
     data/*.csv
```

- **Graph** holds entities, relationships, closed cases, agent cases, and doc chunks with vectors.
- **GraphRAG** = hybrid query: `vectorSearch` over ClosedCase/DocChunk embeddings, then traverse to
  the cards/devices those cases touched. The LLM gets summarized evidence, not raw rows.
- **Case memory** = every agent case is upserted as a `Case` vertex with edges to its card, txns,
  devices, and similar prior cases, plus an embedding. Later investigations retrieve it.
- **Controls**: the agent only sees allowlisted MCP tools (installed queries + vector search +
  one write-back query). No raw `gsql`, no drops. Only `auto` actions are "executed" (mock API);
  L1/L2 actions are queued for approval in the UI.
- **UI**: FastAPI backend + React (Vite) analyst dashboard: case queue, investigation timeline,
  evidence, probability/uncertainty, initial→final actions with approval routes, graph view.

## Phases

1. [ ] Scaffold: pyproject, package layout, .env.example, test harness, git remote.
2. [ ] Data prep: derive card IDs and device profiles, emit vertex/edge files. Tests.
3. [ ] Policy engine + answer schema + validator. Tests.
4. [ ] Hand investigation of cases with pandas to design queries (no answers written by hand).
5. [ ] GSQL schema, loading jobs, installed queries. **Needs Savanna.**
6. [ ] Load graph; embeddings for closed cases + policy/pattern/regulatory docs. **Needs Savanna.**
7. [ ] Agent (LangGraph + MCP + Claude). **Needs ANTHROPIC_API_KEY.**
8. [ ] Run 20 cases → `cases/`; validate; iterate on accuracy.
9. [ ] Optional: monitor Nov–Dec alerts → `cases_extra/`.
10. [ ] UI.
11. [ ] Demo video, blog post, social post.
