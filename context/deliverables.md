# Deliverables and Judging

Sources: `TigerGraph Agentic Fraud Investigation Problem Statement.docx` and `data/README.md`.
When the two disagree, `data/README.md` wins on answer format and policy.

## Submission checklist

- [ ] **Working agent** (runnable from the repo with documented commands)
- [ ] **GitHub repository**
- [ ] **`cases/<case_id>.json`** for all 20 cases in `data/case_pack.csv` (HHG-001 to HHG-020).
      Each file has three parts:
  - [ ] **Case**: internal record (status, verdict, probability, pattern, evidence, affected txns,
        connected cards/devices, exposure, similar prior cases, summary). **Also written to the graph**
        (`written_to_graph: true`, `graph_case_id`).
  - [ ] **SAR** when the policy requires one (`sar.file` must match `FILE_REPORT` in final actions).
  - [ ] **Next best actions** with approval route, recorded **before** (`initial`) and **after**
        (`final`) any requested evidence, plus `what_changed`.
  - [ ] Plus `evidence_requests`, `stop_reason`, `tool_calls`, `tokens`, `latency_s`.
- [ ] **Optional `cases_extra/`**: alerts the agent found itself by monitoring Nov–Dec risk scores
      (Innovation credit only, not accuracy).
- [ ] **3–5 minute demo video**, end to end.
- [ ] **Technical blog post**: what we built, architecture, how TigerGraph is used, agentic capabilities,
      what we learned, what we would improve.
- [ ] **Social post** (X or LinkedIn) tagging @TigerGraphDB, linking blog or demo.

## Required components

| Component | Requirement |
|---|---|
| TigerGraph | Savanna or Community Edition; used for **graph and vector** storage/retrieval |
| GSQL + graph algorithms | Traversal, pattern detection, relationship analysis |
| TigerGraph MCP | Exposes graph capabilities to the agent (`tigergraph/tigergraph-mcp`) |
| GraphRAG | Graph evidence + policy/typology/regulatory text; pass relevant context, not raw data |
| UI | Shows investigation, case progression, evidence, uncertainty, recommendations, next actions |
| Agent framework / LLM | Our choice. LLM for reasoning, tool selection, synthesis, explanation; not a replacement for graph analysis |

Customer messages, card blocks, CRM updates, etc. may be simulated/stubbed/mock APIs.

## Agent capabilities the judges look for

1. Trigger from risk score, customer report, or analyst request.
2. Gather evidence: graph, transaction history, device/identity, account behaviour, prior cases, external data.
3. Identify pattern (5 known + undocumented), assess risk and confidence.
4. Create and progress a case; keep a record of decisions and actions.
5. **Case memory**: retrieve similar past cases, use their outcomes, detect recurring entities across
   cases, write new cases back.
6. Request more evidence via policy-approved actions (customer validation, step-up auth, analyst info),
   with simulated responses.
7. Recommend actions within policy and permissions; only `auto` actions may be executed.
8. Stop when evidence is sufficient (policy section 6).
9. Explain: evidence used, why more evidence was requested, why actions follow (cite rule numbers).

## Judging weights

| Criterion | Weight | What it rewards |
|---|---|---|
| Investigation accuracy | 25% | Correct pattern, affected txns, connected cards, evidence quality |
| Next best action | 25% | Right actions and routes; handling uncertainty; knowing when more evidence is needed; updating after evidence; case-only vs case+SAR |
| Agentic design & engineering | 15% | Architecture, tool use, orchestration, memory, controls, permissions |
| Innovation | 15% | Original use of graph, AI, GraphRAG, agentic capabilities; undocumented pattern discovery; `cases_extra/` |
| Case summary & explainability | 10% | Case creation/progression, summary clarity, evidence, reasoning |
| Demo quality | 10% | Clear end-to-end demo |

`fraud_probability` is scored for **calibration**. `uncertain` earns full credit on designed-ambiguous
cases if actions follow R1 and R8. Half the benchmark cases are legitimate.

## Timeline and event context (verify with organizers)

- Hacker House Goa 2026 runs Oct 28–31, 2026. The briefing notes that HHGOA's public rules say
  "all code must be written during the event" (planning beforehand is allowed). This problem
  statement may be a Partner Trial / selection task with different rules. **Confirm which applies
  before relying on pre-written code.**
- Support: TigerGraph Discord, Devanshu (TigerGraph DevRel).
