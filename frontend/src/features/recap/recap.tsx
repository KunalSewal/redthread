import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Columns3, X } from 'lucide-react'
import { useDefaultLayout, useGroupRef, type LayoutStorage } from 'react-resizable-panels'
import { ErrorState, Id, Loading } from '@/components/states'
import { VerdictBadge } from '@/components/verdict'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'
import { Peers, Run } from '@/features/case/scheme'
import { buildRecapGraph, GraphLegend, RecapGraph, type RecapNode } from '@/features/recap/recap-graph'
import { describe, facts, parseActions } from '@/features/recap/steps'
import { schemeEvidence, type CaseDetail, type Replay, type ReplayStep } from '@/lib/api'
import { action, approvalLevel, basis, prob, trigger } from '@/lib/format'
import { useReplay } from '@/lib/queries'
import { cn } from '@/lib/utils'

/* The three panels can be dragged wider or narrower; the steps and the explanation can be dragged shut to
 * give the graph the whole screen. The widths are a per-viewer convenience kept in localStorage. */
const DEFAULT_LAYOUT = { steps: 20, graph: 50, explanation: 30 }
const HANDLE = 'w-1.5 bg-border/60 transition-colors hover:bg-foreground/20 data-[separator=active]:bg-foreground/30'

const STORAGE: LayoutStorage = {
  getItem: (k) => {
    try {
      return localStorage.getItem(k)
    } catch {
      return null
    }
  },
  setItem: (k, v) => {
    try {
      localStorage.setItem(k, v)
    } catch {
      /* storage blocked: the widths last for this visit */
    }
  },
}

/** Resizable panels need room; below a laptop width the recap stacks instead. */
function useWide() {
  const query = '(min-width: 1024px)'
  const [wide, setWide] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const m = window.matchMedia(query)
    const on = (e: MediaQueryListEvent) => setWide(e.matches)
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [])
  return wide
}

/** A step-by-step recap of one investigation. A clicker, not a video: Next adds the next step. */
export function Recap({
  detail,
  open,
  step,
  onStep,
  onClose,
}: {
  detail: CaseDetail
  open: boolean
  step: number
  onStep: (step: number) => void
  onClose: () => void
}) {
  const replay = useReplay(detail.alert.case_id)

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        showCloseButton={false}
        className="top-0 left-0 flex h-svh w-screen max-w-none translate-x-0 translate-y-0 flex-col gap-0 rounded-none p-0 ring-0 sm:max-w-none"
      >
        <DialogTitle className="sr-only">Recap of {detail.alert.case_id}</DialogTitle>
        <DialogDescription className="sr-only">
          Step through how the agent investigated this case. Use the left and right arrow keys.
        </DialogDescription>
        {replay.isPending ? (
          <div className="p-8">
            <Loading rows={6} />
          </div>
        ) : replay.isError ? (
          <div className="space-y-4 p-8">
            <ErrorState error={replay.error} title="This case has no step-by-step record" />
            <Button variant="outline" onClick={onClose}>
              Close
            </Button>
          </div>
        ) : (
          <RecapBody detail={detail} replay={replay.data} step={step} onStep={onStep} onClose={onClose} />
        )}
      </DialogContent>
    </Dialog>
  )
}

function RecapBody({
  detail,
  replay,
  step,
  onStep,
  onClose,
}: {
  detail: CaseDetail
  replay: Replay
  step: number
  onStep: (step: number) => void
  onClose: () => void
}) {
  const steps = replay.steps
  const index = Math.min(Math.max(0, step - 1), steps.length - 1)
  const current = steps[index]
  const graph = useMemo(() => buildRecapGraph(detail, replay), [detail, replay])
  const verdictStep = steps.find((s) => s.kind === 'assessment')?.step ?? null
  const listRef = useRef<HTMLOListElement>(null)

  const go = useCallback((i: number) => onStep(Math.min(steps.length, Math.max(1, i))), [onStep, steps.length])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault()
        go(index + 2)
      } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault()
        go(index)
      }
    }
    // Capture phase: the dialog handles keys itself before they would bubble up to the window.
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [go, index])

  useEffect(() => {
    listRef.current?.lastElementChild?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [index])

  const fresh = graph.nodes.filter((n) => n.step === current.step)
  const known = graph.nodes.filter((n) => n.step <= current.step).length
  const wide = useWide()
  const groupRef = useGroupRef()
  const layout = useDefaultLayout({ id: 'redthread.recap', storage: STORAGE, onlySaveAfterUserInteractions: true })

  const stepsPanel = (
    <nav className="h-full overflow-y-auto" aria-label="Steps so far">
      <ol ref={listRef} className="space-y-0.5 p-3">
        {steps.slice(0, index + 1).map((s, i) => (
          <li key={s.step} className="recap-in">
            <button
              type="button"
              onClick={() => go(i + 1)}
              aria-current={i === index ? 'step' : undefined}
              className={cn(
                'flex w-full items-start gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50',
                i === index ? 'bg-muted font-medium' : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground',
              )}
            >
              <span className="tnum w-5 shrink-0 text-right text-xs leading-5 text-muted-foreground">{s.step}</span>
              <span className="leading-5">{describe(s).title}</span>
            </button>
          </li>
        ))}
      </ol>
    </nav>
  )

  const graphPanel = (
    <section className="flex h-full min-w-0 flex-col" aria-label="What the agent knew">
      <div className="min-h-0 flex-1 p-4">
        <RecapGraph
          nodes={graph.nodes}
          edges={graph.edges}
          center={detail.alert.card_id}
          step={current.step}
          verdictStep={verdictStep}
          verdict={detail.answer?.case.verdict}
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t px-4 py-3">
        <GraphLegend />
        <span className="tnum text-xs text-muted-foreground">{known} things known so far</span>
      </div>
    </section>
  )

  const explanationPanel = (
    <aside className="h-full overflow-y-auto" aria-live="polite">
      <Explanation key={current.step} detail={detail} replay={replay} step={current} fresh={fresh} verdictStep={verdictStep} />
    </aside>
  )

  return (
    <>
      <header className="flex h-16 shrink-0 items-center gap-4 border-b px-4 sm:px-6">
        <div className="min-w-0">
          <p className="truncate font-semibold">
            Recap of <span className="font-mono">{detail.alert.case_id}</span>
          </p>
          <p className="truncate text-sm text-muted-foreground">
            {trigger(detail.alert.trigger_type)}, how the agent investigated it
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {wide && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => groupRef.current?.setLayout(DEFAULT_LAYOUT)}
              title="Put the three panels back to their usual widths"
            >
              <Columns3 />
              Reset panels
            </Button>
          )}
          <span className="tnum hidden text-sm text-muted-foreground sm:inline">
            Step {current.step} of {steps.length}
          </span>
          <Button variant="outline" onClick={() => go(index)} disabled={index === 0}>
            <ChevronLeft />
            Previous
          </Button>
          {index >= steps.length - 1 ? (
            <Button onClick={onClose}>Finish</Button>
          ) : (
            <Button onClick={() => go(index + 2)}>
              Next
              <ChevronRight />
            </Button>
          )}
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close the recap">
            <X />
          </Button>
        </div>
      </header>

      <div className="h-0.5 shrink-0 bg-muted">
        <div className="h-full bg-foreground transition-[width] duration-300" style={{ width: `${((index + 1) / steps.length) * 100}%` }} />
      </div>

      {wide ? (
        <ResizablePanelGroup
          id="recap"
          groupRef={groupRef}
          defaultLayout={layout.defaultLayout}
          onLayoutChanged={layout.onLayoutChanged}
          className="min-h-0 flex-1"
        >
          <ResizablePanel id="steps" defaultSize="20%" minSize="12%" maxSize="35%" collapsible collapsedSize="0%">
            {stepsPanel}
          </ResizablePanel>
          <ResizableHandle withHandle className={HANDLE} />
          <ResizablePanel id="graph" defaultSize="50%" minSize="25%">
            {graphPanel}
          </ResizablePanel>
          <ResizableHandle withHandle className={HANDLE} />
          <ResizablePanel id="explanation" defaultSize="30%" minSize="20%" maxSize="55%" collapsible collapsedSize="0%">
            {explanationPanel}
          </ResizablePanel>
        </ResizablePanelGroup>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-1 overflow-y-auto">
          <div className="h-[55svh] border-b">{graphPanel}</div>
          {explanationPanel}
        </div>
      )}
    </>
  )
}

function Explanation({
  detail,
  replay,
  step,
  fresh,
  verdictStep,
}: {
  detail: CaseDetail
  replay: Replay
  step: ReplayStep
  fresh: RecapNode[]
  verdictStep: number | null
}) {
  const { title, why } = describe(step)
  const { shift, peers } = schemeEvidence(detail)
  const actions = step.kind === 'recommendation' ? parseActions(step.detail) : []
  const found = step.kind === 'evidence' && step.tool !== 'activity_shift' && step.tool !== 'scheme_peers' ? facts(step.returned) : []

  return (
    <div className="recap-in space-y-6 p-6">
      <div className="space-y-2">
        <p className="tnum text-sm text-muted-foreground">Step {step.step}</p>
        <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
        {why && <p className="leading-relaxed text-muted-foreground">{why}</p>}
      </div>

      <Belief step={step} verdictStep={verdictStep} verdict={detail.answer?.case.verdict} />

      {step.kind === 'alert' && <Quote text={detail.alert.trigger_text} />}

      {step.kind === 'quarantined' && (
        <Section title="What was set aside">
          <ul className="space-y-2">
            {replay.quarantined.map((q, i) => (
              <li key={i} className="rounded-lg border border-dashed px-3 py-2 text-sm">
                “{q.text}”
              </li>
            ))}
          </ul>
        </Section>
      )}

      {step.query && (
        <Section title="The query it ran">
          <p className="text-sm">
            <Id>{step.query}</Id>
          </p>
          {step.parameters && <p className="text-sm break-words text-muted-foreground">{step.parameters}</p>}
        </Section>
      )}

      {step.tool === 'activity_shift' && shift && (
        <Section title="What came back">
          <Run shift={shift} />
        </Section>
      )}
      {step.tool === 'scheme_peers' && peers && (
        <Section title="What came back">
          <Peers peers={peers} />
        </Section>
      )}
      {found.length > 0 && (
        <Section title="What came back">
          <dl className="divide-y rounded-lg border text-sm">
            {found.map((f) => (
              <div key={f.label} className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 px-3 py-2">
                <dt className="text-muted-foreground">{f.label}</dt>
                <dd className="tnum text-right font-medium break-words">{f.value}</dd>
              </div>
            ))}
          </dl>
        </Section>
      )}

      {actions.length > 0 && (
        <Section title="What it recommended">
          <ul className="space-y-1.5">
            {actions.map((a) => (
              <li key={a.label} className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm">
                <span>{a.label}</span>
                <span className="shrink-0 text-xs text-muted-foreground">{approvalLevel(a.route as 'auto').label}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {step.kind === 'assessment' && detail.belief ? (
        <Section title="How each finding counted">
          <p className="text-sm text-muted-foreground">
            It started at {prob(detail.belief.prior)}, because {detail.belief.prior_reason}.
          </p>
          <ul className="divide-y rounded-lg border text-sm">
            {detail.belief.ledger
              .filter((l) => l.counted)
              .map((l, i) => (
                <li key={i} className="flex items-center justify-between gap-3 px-3 py-2">
                  <span className={cn('flex items-center gap-1.5', l.direction === 'incriminating' ? 'text-fraud' : 'text-cleared')}>
                    {l.direction === 'incriminating' ? <ArrowUp className="size-3.5" /> : <ArrowDown className="size-3.5" />}
                    <span className="text-foreground">{basis(l.basis)}</span>
                    <span className="text-muted-foreground">{l.strength}</span>
                  </span>
                  <span className="tnum text-muted-foreground">×{l.lr.toFixed(2)}</span>
                </li>
              ))}
          </ul>
        </Section>
      ) : (
        !step.query &&
        !['alert', 'quarantined', 'recommendation'].includes(step.kind) &&
        step.detail && (
          <Section title="What it recorded">
            <p className="text-sm leading-relaxed">{plain(step.detail)}</p>
          </Section>
        )
      )}

      {fresh.length > 0 && (
        <Section title="New in the graph">
          <div className="flex flex-wrap gap-1">
            {fresh.slice(0, 16).map((n) => (
              <Id key={n.id}>{n.id.replace(/^(scheme|case):/, '')}</Id>
            ))}
            {fresh.length > 16 && <span className="text-sm text-muted-foreground">and {fresh.length - 16} more</span>}
          </div>
        </Section>
      )}
    </div>
  )
}

/** Where the probability stood: a line of every step so far, and what this step did to it. */
function Belief({ step, verdictStep, verdict }: { step: ReplayStep; verdictStep: number | null; verdict?: string }) {
  const reached = verdictStep != null && step.step >= verdictStep

  return (
    <div className="space-y-3 rounded-xl border p-4">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm text-muted-foreground">Probability of fraud</span>
        {reached ? (
          <span className="flex items-center gap-2">
            <VerdictBadge verdict={verdict} />
            <span className="tnum text-lg font-semibold">{prob(step.probability)}</span>
          </span>
        ) : (
          <span className="text-sm">Not weighed yet</span>
        )}
      </div>
      <div className="space-y-1.5" aria-hidden="true">
        <div className="relative h-2 rounded-full bg-muted">
          {reached && step.probability != null && (
            <div
              className={cn(
                'absolute inset-y-0 left-0 rounded-full transition-[width] duration-500',
                verdict === 'fraud' ? 'bg-fraud' : verdict === 'legitimate' ? 'bg-cleared' : 'bg-muted-foreground/60',
              )}
              style={{ width: `${step.probability * 100}%` }}
            />
          )}
          {reached && step.moved?.from != null && (
            <div className="absolute -inset-y-1 w-0.5 rounded bg-foreground/70" style={{ left: `${step.moved.from * 100}%` }} title="Where it started" />
          )}
        </div>
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>0, clearly legitimate</span>
          <span>1, clearly fraud</span>
        </div>
      </div>
      <p className="text-sm leading-relaxed text-muted-foreground">
        {step.moved
          ? `Moved from ${prob(step.moved.from)} to ${prob(step.moved.to)}: ${step.moved.because}.`
          : reached
            ? 'This step did not move it.'
            : 'The agent gathers evidence first; code weighs it all at once.'}
      </p>
    </div>
  )
}

/** Backend notes name policy actions by identifier and use "->"; say them in words. */
function plain(text: string) {
  return text
    .replace(/\b[A-Z]{2,}(?:_[A-Z]+)+\b/g, (id) => action(id).toLowerCase())
    .replace(/\s*->\s*/g, ' to ')
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-medium">{title}</h3>
      {children}
    </section>
  )
}

function Quote({ text }: { text: string }) {
  return <blockquote className="rounded-lg bg-muted/50 px-4 py-3 text-sm leading-relaxed">{text}</blockquote>
}
