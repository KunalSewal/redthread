import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { ChevronLeft, ListOrdered, ShieldAlert } from 'lucide-react'
import { ErrorState, Id, Loading } from '@/components/states'
import { ProbabilityBar, VerdictBadge } from '@/components/verdict'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DecisionsTab } from '@/features/case/decisions'
import { EvidenceTab } from '@/features/case/evidence'
import { ReportTab } from '@/features/case/report'
import { SummaryTab } from '@/features/case/summary'
import { Recap } from '@/features/recap/recap'
import { dateTime, money, pattern, source, status, trigger } from '@/lib/format'
import { useCase } from '@/lib/queries'

export function CaseView({ caseId, onBack }: { caseId: string; onBack: () => void }) {
  const q = useCase(caseId)
  const [tab, setTab] = useState('summary')
  const [params, setParams] = useSearchParams()
  const recapStep = Number(params.get('recap')) || 0

  function setRecap(step: number | null) {
    const next = new URLSearchParams(params)
    if (step == null) next.delete('recap')
    else next.set('recap', String(step))
    setParams(next, { replace: true })
  }

  if (q.isPending) return <Loading rows={8} />
  if (q.isError) return <ErrorState error={q.error} title={`${caseId} could not be loaded`} />

  const d = q.data
  const c = d.answer?.case
  const setAside = d.events.filter((e) => e.kind === 'quarantined').length
  const waiting = d.actions.filter((a) => a.route !== 'auto' && a.state === 'awaiting approval').length

  return (
    <article className="space-y-5" aria-labelledby="case-title">
      <Button variant="ghost" size="sm" className="-ml-2 lg:hidden" onClick={onBack}>
        <ChevronLeft />
        All cases
      </Button>

      <header className="space-y-4 rounded-xl border bg-card p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2.5">
              <h2 id="case-title" className="font-mono text-xl font-semibold">
                {d.alert.case_id}
              </h2>
              <VerdictBadge verdict={c?.verdict} />
              {c && <span className="text-sm text-muted-foreground">{status(c.status)}</span>}
            </div>
            <p className="text-sm text-muted-foreground">
              {trigger(d.alert.trigger_type)} on {dateTime(d.alert.opened_at)}. {source(d.alert.source)}.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {waiting > 0 && (
              <Button variant="outline" onClick={() => setTab('decisions')}>
                {waiting} {waiting === 1 ? 'decision' : 'decisions'} waiting on you
              </Button>
            )}
            {d.answer && (
              <Button onClick={() => setRecap(1)}>
                <ListOrdered />
                Show recap
              </Button>
            )}
          </div>
        </div>

        <dl className="grid gap-4 border-t pt-4 sm:grid-cols-2 xl:grid-cols-4">
          <Fact label="Probability of fraud">
            <ProbabilityBar value={c?.fraud_probability} />
          </Fact>
          <Fact label="Pattern">{pattern(c?.pattern)}</Fact>
          <Fact label="Money at risk">
            <span className="tnum">{money(c?.exposure_usd, true)}</span>
          </Fact>
          <Fact label="Flagged">
            <span className="flex flex-wrap gap-1">
              <Id>{d.alert.flagged_txn_id}</Id>
              <Id>{d.alert.card_id}</Id>
            </span>
          </Fact>
        </dl>

        <blockquote className="rounded-lg bg-muted/50 px-4 py-3 text-sm">
          <p className="mb-1 text-xs text-muted-foreground">The alert as it arrived</p>
          <p className="whitespace-pre-line">{d.alert.trigger_text}</p>
          {setAside > 0 && (
            <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
              <ShieldAlert className="size-3.5 text-caution" />
              Part of this text was addressed to the agent, not to an analyst. It was set aside and never acted on.
            </p>
          )}
        </blockquote>
      </header>

      {!d.answer ? (
        <p className="rounded-xl border border-dashed p-8 text-center text-muted-foreground">
          The agent has not investigated this alert yet.
        </p>
      ) : (
        <Tabs value={tab} onValueChange={(v) => setTab(String(v))}>
          <TabsList variant="line" className="h-auto! w-full flex-wrap justify-start border-b pb-0 *:flex-none *:px-3">
            <TabsTrigger value="summary">Summary</TabsTrigger>
            <TabsTrigger value="evidence">Evidence</TabsTrigger>
            <TabsTrigger value="decisions">Decisions</TabsTrigger>
            <TabsTrigger value="report">Report</TabsTrigger>
          </TabsList>
          <TabsContent value="summary" className="pt-4">
            <SummaryTab detail={d} onOpenDecisions={() => setTab('decisions')} />
          </TabsContent>
          <TabsContent value="evidence" className="pt-4">
            <EvidenceTab detail={d} />
          </TabsContent>
          <TabsContent value="decisions" className="pt-4">
            <DecisionsTab detail={d} />
          </TabsContent>
          <TabsContent value="report" className="pt-4">
            <ReportTab detail={d} />
          </TabsContent>
        </Tabs>
      )}
      {d.answer && <Recap detail={d} open={recapStep > 0} step={recapStep || 1} onStep={setRecap} onClose={() => setRecap(null)} />}
    </article>
  )
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="font-medium">{children}</dd>
    </div>
  )
}
