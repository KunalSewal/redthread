# Demo video script (3–5 minutes)

Written for whoever records the video. Timings are a guide. Everything below is real and on screen:
no slides of claims we cannot show running.

## Before recording

1. Start the Savanna workspace and wait until it is running (auto-suspend will have stopped it).
   **If you would rather not depend on it, you do not have to** — see "Recording without the
   workspace" at the end. Everything except the live investigation runs from files.
2. `python -m uvicorn redthread.api.app:app --port 8000`
3. `cd ui && npx vite`
4. Open `http://localhost:5173` at 1440×900 or larger. Close other tabs.
5. Open `/case/HHG-014` once to warm it, then go back to `/`.
6. If you want the live investigation beat, delete `cases/HHG-016.json` first so the docket shows it
   as "not investigated". It takes about 90 seconds to run, which is most of a minute of video — skip
   it if you are tight, and use the replay beat instead.

## The five beats

Each beat is one page. The whole thing is one continuous move: docket → case → what the queue missed
→ rings → should you believe it.

---

**0:00–0:30 — The docket**

Open on `/`.

> "Twenty fraud alerts. About half are legitimate, and the bank's own risk score is wrong in both
> directions — above 0.85 it is right about a third of the time. The job is not a fraud score. It is a
> decision the bank can defend to a regulator."

Scroll to the second group.

> "These twenty-five nobody asked for. The agent raised them itself, between the alerts."

---

**0:30–1:45 — One case, and how it got there (HHG-014)**

Click **HHG-014**.

> "An analyst asked about several cards using the same unusual device. Our own fraud model scored the
> flagged transaction 0.0065 — invisible. Every per-transaction model would wave this through."

Point at the verdict line, then the graph.

> "In the graph, that one Samsung profile connects twenty-one cards that month, every one of them with
> the device new to the account and behind an anonymous proxy, and four of them already carry
> confirmed-fraud cases. The signature lives across accounts, which is exactly what a per-transaction
> model cannot see."

**Now the part to slow down for.** Click on the thread, then press `←` a few times.

> "This is the investigation, one step per node. The arrow keys walk it backwards — and the whole case
> file walks back with it. The graph drops to what the agent had actually found by that step. The
> probability scale says 'no estimate yet', because at that point it genuinely had not formed one."

Press `End` to return to the finished case.

> "Nothing here is a reconstruction. It is the stored trace."

---

**1:45–2:45 — Why the probability is what it is**

Scroll to **Why the probability is what it is**.

> "The agent does not state a probability. It judges each finding — which way it points, how strong it
> is, and what it rests on — and the code does the Bayes. Every line is here, with what it was worth."

Point at a line marked *halved*.

> "These two rest on the same device, so the second one counts for half. Three findings about one
> device are not three independent reasons to block a customer's card."

**Untick the strongest incriminating line.** Wait for the recomputed line underneath.

> "And because the arithmetic is deterministic, you can take evidence away. The probability recomputes,
> and so does the recommended action — no model call, same functions the agent used. That is the
> difference between an explanation and a story told afterwards."

Re-tick it.

---

**2:45–3:20 — What the queue missed**

Go to **What the queue missed**.

> "Between the alerts it was handed, the agent swept the graph itself. Twenty-five cases nobody
> queued. It called fraud in fourteen, worth three thousand nine hundred dollars, and left eleven
> uncertain for a person rather than guessing."

Point at the low scores column.

> "The bank scored nineteen of these below 0.30 and let them through. Three of them are charges of
> about a hundred and fifty dollars on different cards through the same devices. A model sees three
> ordinary purchases. The graph sees one operator."

---

**3:20–4:20 — Should you believe it**

Go to **Should you believe it**. This beat is the point of the whole video; do not rush it.

> "We built our own exam, because the answer key is hidden. It scored twenty-four out of twenty-four.
> Then we read our own test harness and found we had set the alert type from the outcome — every
> confirmed fraud arrived as a customer complaint, every cleared case as a model alert. The alert type
> *was* the answer. An agent that ignored the graph entirely would also have scored twenty-four out of
> twenty-four."

Point at the results.

> "On an honest version, the same pipeline scored fifty-nine per cent, with a calibration score worse
> than guessing — because the wrong answers came out at 0.97. Two real defects were hiding behind
> that: evidence that multiplied itself into certainty, and a simulated customer reply that was picked
> from the agent's own belief and then scored as evidence against it."

> "Fixed: seventy-five per cent, and legitimate customers wrongly accused of fraud fell from seventeen
> to six. The number I care about most is that it now answers 'uncertain' on seventeen of sixty cases
> and escalates them to a person, instead of confidently guessing."

Scroll to the pattern table and the two orange rows.

> "And here is where it is still weak. Card testing, recall 0.062. We put our failures in the product,
> because an analyst needs to know when to check the work themselves."

---

**Close (optional, 10s)**

> "TigerGraph for the graph and the vectors, through the official MCP server. GSQL for every query.
> The policy engine decides the actions; the model never picks an approval route."

## Recording without the workspace

`/case/HHG-014?replay=1` walks the stored trace through the same views automatically, about 400ms a
step. It is the real trace, not a mock, so you can record the whole case beat with Savanna suspended
and no API key. The only beat that needs a live workspace is clicking **Investigate**.

## If something goes wrong on camera

- A panel showing "could not be displayed" is contained on purpose — the rest of the case is fine.
  Carry on; do not reload.
- If the API is not running, every page shows a single clear error naming the uvicorn command.
- Approvals write to `runs/approvals.json`. Delete it to reset the queue between takes.
