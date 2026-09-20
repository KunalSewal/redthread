# Demo video script (3–5 minutes)

Written for whoever records the video. Timings are a guide. Everything below is real: no slides of
claims we can't show running.

**Before recording**
1. Start the Savanna workspace and wait until it is running (auto-suspend will have stopped it).
2. `python -m uvicorn redthread.api.app:app --port 8000`, then `cd ui && npx vite`.
3. Open `http://localhost:5173`, pick HHG-014, and check the case loads.
4. Pick a case to investigate live. HHG-016 is a good choice: about a minute, and the verdict changes
   nothing that is already on screen. Delete its answer file first if you want the queue to show
   "Not investigated".
5. Close other tabs; 1440×900 or larger.

---

**0:00–0:25 — The problem, on screen**

Open on the queue. "Twenty fraud alerts. Half of them are legitimate, and the bank's own risk score
is wrong in both directions: above 0.85 it is right about a third of the time. The job isn't a fraud
score, it's a decision the bank can defend."

**0:25–1:05 — Watch it investigate (HHG-016)**

Click **Investigate**. While the thread fills in: "RedThread reaches TigerGraph only through the
official MCP server, and only through installed GSQL queries. It runs the same evidence checklist
every time — the alert's context, the card's window, the resolved account holder's baseline, the
device's neighbourhood, shared-origin lift, linked and similar cases — and then asks for whatever
else it needs."

Let the verdict land. Point at the probability scale: "the thresholds are the policy's own: 0.30
opens a case, 0.70 is the line for blocking on a single signal, 0.85 is decisive."

**1:05–1:55 — The case the model could not see (HHG-014)**

Switch to HHG-014. "An analyst asks about several cards using the same unusual device. Our
transaction model scores this one 0.0065 — invisible."

Scroll to the evidence, then the graph. "In the graph, twenty-one cards used that Samsung profile
that month, every one of them with the device new to the account and behind a proxy, and four closed
cases from August name the same device. The bank's analysts couldn't fit those to a typology either:
they labelled them undocumented. The agent reaches the same conclusion, files a report under rule R9
and escalates."

Hover a red edge. "Red is the thread: links into the fraud itself."

**1:55–2:30 — Uncertainty and changing your mind (HHG-001)**

Switch to HHG-001. "The bank scored this 0.61. The holder's own history shows the same $77 purchase
in the same region every week. Rather than close over the customer, the agent verifies, and the
recommendation changes: before, verify and open a case; after, warn and close. Both are recorded,
with the assumption it made about the reply spelled out, because the dataset gives us no real
customer replies."

**2:30–3:05 — Controls (any fraud case)**

Show the approvals panel. "The agent executes only what policy lets it execute. Blocking a card
waits for a team lead; filing a report waits for a fraud manager. The server refuses an L1 approval
on an L2 action." Approve one action to show the state change.

**3:05–3:45 — Why it gets things right**

Show the case-memory point: "Every case is written back into the graph with its evidence and
timeline, so the next investigation can retrieve it."

Then the two measured claims (numbers from `runs/backtest.json` and
`data/processed/pattern_eval.json`): "We can't see the answer key, so we built our own exam: replay
closed October cases as fresh alerts, hiding anything from that date on. Verdict accuracy N%, with
every cleared case correctly cleared. And because the five documented patterns are mechanical
properties of an episode, we derive the pattern in code: 96% agreement with the bank's analysts
across all 4,665 confirmed-fraud cases."

**3:45–4:00 — Close**

"TigerGraph for the graph, the vectors and the case memory; MCP for tool access; the LLM for
reasoning and explanation; the policy in code so the decisions are defensible. Repository in the
description."

---

**Do not claim on camera**
- Any accuracy on the 20 benchmark cases. We do not have the key.
- That customer replies are real. They are simulated, and the answer files say so.
