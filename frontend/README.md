# RedThread frontend

The analyst workbench: a landing page, a dashboard, and a case workspace. React, TypeScript, Vite,
Tailwind and shadcn/ui, with light and dark themes. `ui/` is the earlier workbench and is left as it is.

## Run it

**From the recorded snapshot** (no backend, data or keys needed; read-only):

```bash
cd frontend
npm install
npm run dev:mock        # http://localhost:5180
```

It reads `../ui/mock/api/*.json`, the snapshot the backend writes with `python scripts/snapshot_api.py`.
A fresh snapshot shows up here without any change on this side. Approving, challenging and
investigating return a clear message instead of being faked.

**Against the live backend** (approvals, challenges, what-if and live investigations work):

```bash
.venv/bin/python -m uvicorn redthread.api.app:app --port 8000   # repo root
cd frontend && npm run dev                                       # http://localhost:5181, proxies /api to :8000
```

Signing in takes an analyst key from `python scripts/approvers.py add --name "..." --role L2`. The UI has
one role, the analyst; give every analyst an L2 key. Settling a contested challenge needs a second,
different analyst, so a demo needs two keys.

Before pushing: `npm run typecheck` and `npm run lint`.

## Pages

| Route | What it is for |
|---|---|
| `/` | Landing page: what RedThread does, one real case drawn as a thread, the headline results |
| `/app` | Dashboard. Overview (counts, what needs a decision, verdicts, patterns), rings and containment, and the trust evidence |
| `/app/cases/:id?` | Case workspace: a paged case list on the left; the case on the right with Summary, Evidence, Decisions, How it investigated, and Report |

## Where things live

- `src/lib/api.ts`: every backend type and call. The backend is the source of truth for these shapes.
- `src/lib/format.ts`: plain-language labels for policy actions, patterns, triggers and approval levels.
- `src/pages/`: the three pages. `src/features/`: the dashboard tabs and the case tabs.
- `src/index.css`: theme tokens. Fraud red (`--fraud`) marks fraud and nothing else; uncertain has no colour.
