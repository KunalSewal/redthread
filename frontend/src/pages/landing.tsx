import { Link } from 'react-router'
import { Brand } from '@/components/brand'
import { ThemeToggle } from '@/components/theme-toggle'
import { Button } from '@/components/ui/button'
import { schemeEvidence, type CaseDetail } from '@/lib/api'
import { action, count, isBankQueue, money, pattern, prob, trigger } from '@/lib/format'
import { useCase, useCases, useEvaluation } from '@/lib/queries'

const SHOWCASE = 'HHF-004'

export function LandingPage() {
  return (
    <div className="min-h-svh bg-background">
      <header className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        <Brand />
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Button render={<Link to="/app" />}>Open the workbench</Button>
        </div>
      </header>

      <main>
        <section className="mx-auto max-w-6xl px-4 pt-14 pb-10 sm:px-6 sm:pt-20">
          <h1 className="max-w-[18ch] text-4xl leading-[1.08] font-semibold tracking-tight text-balance sm:text-6xl">
            Every fraud leaves a thread.
          </h1>
          <p className="mt-6 max-w-[58ch] text-lg leading-relaxed text-muted-foreground">
            RedThread is the investigator that pulls it, and shows its work. It takes an alert, follows it across a graph of
            650,938 card transactions, decides what happened under the bank's fraud policy, and hands the analyst every ID behind
            every claim. A person approves anything that touches a customer.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button size="lg" className="h-11 px-5 text-base" render={<Link to="/app" />}>
              Open the workbench
            </Button>
            <Button size="lg" variant="outline" className="h-11 px-5 text-base" render={<Link to={`/app/cases/${SHOWCASE}?recap=1`} />}>
              Follow one case, step by step
            </Button>
          </div>
        </section>

        <ThreadHero />
        <Results />
        <HowItWorks />
        <Controls />
      </main>

      <footer className="border-t">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-8 text-sm text-muted-foreground sm:px-6">
          <span>Built for the TigerGraph agentic fraud investigation challenge, Hacker House Goa 2026.</span>
          <Link to="/app" className="font-medium text-foreground hover:underline">
            Open the workbench
          </Link>
        </div>
      </footer>
    </div>
  )
}

/** One real case drawn as a thread: from the alert to the decision waiting on a person. */
function ThreadHero() {
  const q = useCase(SHOWCASE)
  const knots = q.data ? knotsFor(q.data) : null

  return (
    <section className="border-y bg-muted/30" aria-label={`How case ${SHOWCASE} was investigated`}>
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
        <div className="mb-8 flex flex-wrap items-baseline justify-between gap-2">
          <p className="font-medium">
            Case <span className="font-mono">{SHOWCASE}</span>, as the agent investigated it
          </p>
          <Link to={`/app/cases/${SHOWCASE}`} className="text-sm text-muted-foreground hover:text-foreground hover:underline">
            Open this case
          </Link>
        </div>

        {!knots ? (
          <div className="h-56 animate-pulse rounded-xl bg-muted" />
        ) : (
          <div className="relative">
            <div className="thread-draw absolute top-[11px] right-0 left-3 hidden h-0.5 origin-left bg-fraud md:block" aria-hidden="true" />
            <ol className="relative grid gap-8 md:grid-cols-5 md:gap-6">
              {knots.map((k) => (
                <li key={k.title} className="relative space-y-2 border-l-2 border-fraud pl-5 md:border-l-0 md:pl-0">
                  <span className="relative z-10 hidden size-6 rounded-full border-2 border-fraud bg-background md:block" aria-hidden="true" />
                  <p className="text-sm text-muted-foreground md:pt-3">{k.title}</p>
                  <p className="tnum text-2xl font-semibold tracking-tight">{k.figure}</p>
                  <p className="max-w-[30ch] text-sm leading-relaxed text-foreground/80">{k.text}</p>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </section>
  )
}

function knotsFor(d: CaseDetail) {
  const c = d.answer?.case
  const { shift, peers } = schemeEvidence(d)
  const waiting = d.actions.filter((a) => a.route !== 'auto' && a.state === 'awaiting approval')
  return [
    {
      title: 'The alert',
      figure: trigger(d.alert.trigger_type),
      text:
        d.alert.trigger_type === 'customer_report'
          ? 'The cardholder says they did not make these charges.'
          : d.alert.trigger_type === 'analyst_request'
            ? 'An analyst asked for this card to be looked at.'
            : "The bank's model scored a charge as risky.",
    },
    {
      title: 'What the card had never done',
      figure: shift ? `${shift.run.length} charges` : 'None found',
      text: shift ? `Small online charges totalling ${money(shift.run_total_usd, true)}, unlike anything in its history.` : '',
    },
    {
      title: 'Who else started the same',
      figure: peers ? `${peers.other_cards_now} cards` : 'None found',
      text: peers
        ? `Against ${peers.other_cards_month_before} and ${peers.other_cards_two_months_before} in the two months before. A scheme, not one card.`
        : '',
    },
    {
      title: 'The verdict',
      figure: c ? prob(c.fraud_probability) : '',
      text: c ? `${pattern(c.pattern)}. The probability is computed by code from each judged finding.` : '',
    },
    {
      title: 'Waiting on a person',
      figure: `${waiting.length} ${waiting.length === 1 ? 'decision' : 'decisions'}`,
      text: waiting.length
        ? `${waiting.map((w, i) => (i ? action(w.action).toLowerCase() : action(w.action))).join(' and ')}.`
        : 'Nothing left to approve.',
    },
  ]
}

function Results() {
  const cases = useCases()
  const evaluation = useEvaluation()
  const bank = (cases.data ?? []).filter((c) => isBankQueue(c.source))
  const raised = (cases.data ?? []).length - bank.length
  const n = (v: string) => bank.filter((c) => c.verdict === v).length
  const drills = Object.values(evaluation.data?.final_round?.drills ?? {})

  const items = [
    { figure: `${bank.filter((c) => c.verdict).length} of ${bank.length}`, text: `Final-round alerts answered: ${n('fraud')} fraud, ${n('uncertain')} uncertain, ${n('legitimate')} legitimate.` },
    { figure: count(raised), text: "Alerts the agent raised on its own that the bank's queue never opened." },
    {
      figure: drills.length ? `${drills.filter((d) => d.passed).length} of ${drills.length}` : 'Not run',
      text: 'Failure drills passed: lost connections, model timeouts, garbage output, hostile text.',
    },
  ]

  return (
    <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
      <h2 className="text-2xl font-semibold tracking-tight">Where it stands</h2>
      <dl className="mt-8 grid gap-8 sm:grid-cols-3">
        {items.map((it) => (
          <div key={it.text} className="space-y-2 border-t pt-4">
            <dt className="tnum text-3xl font-semibold tracking-tight">{cases.isPending ? '' : it.figure}</dt>
            <dd className="max-w-[34ch] leading-relaxed text-muted-foreground">{it.text}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

function HowItWorks() {
  const steps = [
    {
      title: 'It gathers the evidence',
      text: 'Installed graph queries pull the card’s history, its devices, the customers it shares them with, past cases and the policy passages that apply. Nothing after the alert is visible to it.',
    },
    {
      title: 'Code weighs it',
      text: 'The model judges each finding. Deterministic code turns those judgements into a probability, applies the policy, and picks the actions and who must approve them.',
    },
    {
      title: 'A person decides',
      text: 'Anything that blocks a card or files a report waits for an analyst. Disagreeing takes evidence, and every decision is written back to the case in the graph.',
    },
  ]
  return (
    <section className="border-t bg-muted/30">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <h2 className="text-2xl font-semibold tracking-tight">How one investigation runs</h2>
        <ol className="mt-8 grid gap-8 md:grid-cols-3">
          {steps.map((s, i) => (
            <li key={s.title} className="space-y-2">
              <span className="tnum text-sm font-medium text-muted-foreground">Step {i + 1}</span>
              <h3 className="text-lg font-semibold">{s.title}</h3>
              <p className="max-w-[40ch] leading-relaxed text-muted-foreground">{s.text}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}

function Controls() {
  const points = [
    { title: 'Every claim is checkable', text: 'Each line of evidence names the query and parameters behind it and the records it rests on.' },
    { title: 'Text cannot steer it', text: 'Instructions hidden in an alert are set aside before the model sees them, and outcomes are computed, not written.' },
    { title: 'Approvals are enforced', text: 'Decisions come from an analyst’s key, never from the request, and each one is recorded in a tamper-evident log.' },
    { title: 'You can replay any case', text: 'Step through what it saw at each moment, which query it ran, what came back and why the probability moved.' },
  ]
  return (
    <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
      <h2 className="text-2xl font-semibold tracking-tight">Built so a bank can trust it</h2>
      <div className="mt-8 grid gap-x-10 gap-y-8 sm:grid-cols-2">
        {points.map((p) => (
          <div key={p.title} className="space-y-1.5">
            <h3 className="font-semibold">{p.title}</h3>
            <p className="max-w-[48ch] leading-relaxed text-muted-foreground">{p.text}</p>
          </div>
        ))}
      </div>
      <div className="mt-12">
        <Button size="lg" className="h-11 px-5 text-base" render={<Link to="/app" />}>
          Open the workbench
        </Button>
      </div>
    </section>
  )
}
