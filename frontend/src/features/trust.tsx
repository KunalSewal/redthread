import { CheckCircle2, XCircle } from 'lucide-react'
import { Pager, usePaged } from '@/components/pager'
import { ErrorState, Id, Loading } from '@/components/states'
import { VerdictBadge } from '@/components/verdict'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Figure } from '@/features/network'
import type { FinalRound } from '@/lib/api'
import { count, pct, prob } from '@/lib/format'
import { useEvaluation } from '@/lib/queries'
import { cn } from '@/lib/utils'

/* Should you believe it? Everything here was measured by the backend's scripts; the UI only lays it out. */

const DRILLS: Record<string, string> = {
  dependency_fails: 'The graph connection drops mid-run',
  model_timeout: 'The model times out',
  model_garbage: 'The model returns garbage',
  hostile_input: 'Instructions hidden in the alert',
  invalid_input: 'An alert naming no real transaction, or malformed',
  wrong_role: 'A decision made with the wrong key, or none',
  same_case: 'One case investigated twice',
}

export function TrustPanel() {
  const q = useEvaluation()
  if (q.isPending) return <Loading rows={6} />
  if (q.isError) return <ErrorState error={q.error} />
  const fr = q.data.final_round

  return (
    <div className="space-y-6">
      <Backtest baselines={q.data.baselines} backtest={q.data.backtest} />
      <div className="grid gap-6 xl:grid-cols-2">
        <Drills drills={fr?.drills ?? null} />
        <Attacks attacks={fr?.attacks ?? null} />
      </div>
      <Ablation ablation={fr?.ablation ?? null} />
      <DataQuality rows={fr?.data_quality ?? null} />
    </div>
  )
}

function Missing({ what }: { what: string }) {
  return <p className="text-sm text-muted-foreground">{what} has not been measured in this data yet.</p>
}

function Backtest({ baselines, backtest }: { baselines: import('@/lib/api').Baseline[] | null; backtest: import('@/lib/api').Evaluation['backtest'] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Replayed on cases the bank already closed</CardTitle>
        <CardDescription>
          The agent investigated past cases without seeing their outcome, then was scored against what the bank found.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {backtest ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Figure label="Verdicts right" value={pct(backtest.verdict_accuracy)} note={`On ${count(backtest.n)} replayed cases`} />
            <Figure label="Fraud caught" value={pct(backtest.fraud_recall)} note="Of the cases that were fraud" />
            <Figure label="Cleared customers left alone" value={pct(backtest.cleared_accuracy)} note="Of the cases that were not" />
            <Figure label="Probability error" value={prob(backtest.brier)} note="Brier score, lower is better" />
          </div>
        ) : (
          <Missing what="The replay" />
        )}
        {baselines && baselines.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Method, on the same cases</TableHead>
                <TableHead className="text-right">Verdicts right</TableHead>
                <TableHead className="text-right">Fraud caught</TableHead>
                <TableHead className="text-right">Wrongly accused</TableHead>
                <TableHead className="text-right">Left uncertain</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {baselines.map((b) => (
                <TableRow key={b.method} className={cn(b.method.startsWith('RedThread') && 'bg-muted/40 font-medium')}>
                  <TableCell>{b.method.charAt(0).toUpperCase() + b.method.slice(1)}</TableCell>
                  <TableCell className="tnum text-right">{pct(b.verdict_accuracy)}</TableCell>
                  <TableCell className="tnum text-right">{b.fraud_caught == null ? 'None' : pct(b.fraud_caught)}</TableCell>
                  <TableCell className="tnum text-right">{b.wrongly_accused}</TableCell>
                  <TableCell className="tnum text-right">{b.uncertain}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

function Pass({ ok }: { ok: boolean }) {
  return ok ? (
    <span className="inline-flex items-center gap-1 text-sm text-cleared">
      <CheckCircle2 className="size-4" /> Passed
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-sm text-destructive">
      <XCircle className="size-4" /> Failed
    </span>
  )
}

function Drills({ drills }: { drills: FinalRound['drills'] }) {
  const entries = Object.entries(drills ?? {})
  const passed = entries.filter(([, d]) => d.passed).length
  return (
    <Card>
      <CardHeader>
        <CardTitle>Drills</CardTitle>
        <CardDescription>
          {entries.length ? `${passed} of ${entries.length} passed against the live graph and model.` : 'Failures injected on purpose, to check it fails safely.'}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {entries.length === 0 ? (
          <Missing what="The drills" />
        ) : (
          <ul className="divide-y">
            {entries.map(([k, d]) => (
              <li key={k} className="flex items-start justify-between gap-4 py-3">
                <div className="space-y-0.5">
                  <p className="text-sm font-medium">{DRILLS[k] ?? k}</p>
                  <p className="text-sm text-muted-foreground">{describeDrill(d)}</p>
                </div>
                <Pass ok={d.passed} />
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

type Run = { verdict?: string; probability?: number }

function describeDrill(d: Record<string, unknown>) {
  if (d.outcome === 'halted') return `Stopped at ${String(d.stage)}. No answer written, nothing saved.`
  if (d.outcome === 'answered' && typeof d.quarantined === 'number')
    return `${d.quarantined} hidden instructions set aside; answered ${String(d.verdict)}.`
  if (d.status_codes && typeof d.status_codes === 'object') {
    const codes = Object.values(d.status_codes as Record<string, number>).join(', ')
    return `Refused with ${codes}. ${d.decisions_recorded === 0 ? 'No decision was recorded.' : `${String(d.decisions_recorded)} decisions recorded.`}`
  }
  if (d.first && d.second) {
    const [a, b] = [d.first as Run, d.second as Run]
    return `Answered ${a.verdict} at ${prob(a.probability)}, then ${b.verdict} at ${prob(b.probability)}.`
  }
  if (Object.values(d).some((v) => v && typeof v === 'object' && (v as { answer_written?: boolean }).answer_written === false))
    return 'Each one refused before any investigation, with no answer written.'
  return ''
}

function Attacks({ attacks }: { attacks: FinalRound['attacks'] }) {
  const list = Object.values(attacks ?? {})
  return (
    <Card>
      <CardHeader>
        <CardTitle>Attacks</CardTitle>
        <CardDescription>Text planted to talk the agent into a wrong outcome, run with its defences on and off.</CardDescription>
      </CardHeader>
      <CardContent>
        {list.length === 0 ? (
          <Missing what="The attacks" />
        ) : (
          <ul className="divide-y">
            {list.map((a) => {
              const on = a.defended as { verdict?: string; probability?: number; attack_succeeded?: boolean } | undefined
              const off = a.undefended as { verdict?: string; probability?: number; attack_succeeded?: boolean } | undefined
              return (
                <li key={a.id} className="space-y-2 py-3">
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-0.5">
                      <p className="text-sm font-medium">
                        {a.id} on <Id>{a.case}</Id>
                      </p>
                      <p className="text-sm text-muted-foreground">
                        Tries for {a.goal}, through the {a.surface}.
                      </p>
                    </div>
                    <Pass ok={on ? !on.attack_succeeded : false} />
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-sm">
                    <Outcome label="Clean run" verdict={a.clean.verdict} />
                    <Outcome label="Defences on" verdict={on?.verdict} p={on?.probability} />
                    <Outcome label="Defences off" verdict={off?.verdict} p={off?.probability} />
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function Outcome({ label, verdict, p }: { label: string; verdict?: string; p?: number }) {
  return (
    <div className="space-y-1 rounded-md border p-2">
      <p className="text-xs text-muted-foreground">{label}</p>
      <div className="flex items-center gap-2">
        <VerdictBadge verdict={verdict} />
        {p != null && <span className="tnum text-xs text-muted-foreground">{prob(p)}</span>}
      </div>
    </div>
  )
}

const VARIANTS: [string, string][] = [
  ['full', 'As submitted'],
  ['no_detectors', 'Without the new detectors'],
  ['old_priors', "With Round 1's priors"],
  ['neither', 'Without either'],
]

function Ablation({ ablation }: { ablation: FinalRound['ablation'] }) {
  const rows = ablation ?? []
  const paged = usePaged(rows, 6)
  return (
    <Card>
      <CardHeader>
        <CardTitle>What each change contributes</CardTitle>
        <CardDescription>
          Every final-round answer recomputed from its own evidence with one piece taken out. No model call is involved.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <Missing what="The ablation" />
        ) : (
          <>
            <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {VARIANTS.map(([k, label]) => {
                const n = (v: string) => rows.filter((r) => r.verdict[k] === v).length
                return (
                  <div key={k} className="rounded-lg border p-3">
                    <p className="text-sm text-muted-foreground">{label}</p>
                    <p className="tnum mt-1 text-sm">
                      <span className="font-semibold text-fraud">{n('fraud')}</span> fraud,{' '}
                      <span className="font-semibold">{n('uncertain')}</span> uncertain,{' '}
                      <span className="font-semibold text-cleared">{n('legitimate')}</span> legitimate
                    </p>
                  </div>
                )
              })}
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Case</TableHead>
                  {VARIANTS.map(([k, label]) => (
                    <TableHead key={k}>{label}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {paged.visible.map((r) => (
                  <TableRow key={r.case}>
                    <TableCell>
                      <Id>{r.case}</Id>
                    </TableCell>
                    {VARIANTS.map(([k]) => (
                      <TableCell key={k}>
                        <span className="flex items-center gap-2">
                          <VerdictBadge verdict={r.verdict[k]} />
                          <span className="tnum text-xs text-muted-foreground">{prob(r.probability[k])}</span>
                        </span>
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Pager {...paged} />
          </>
        )}
      </CardContent>
    </Card>
  )
}

function DataQuality({ rows }: { rows: FinalRound['data_quality'] }) {
  const list = rows ?? []
  const paged = usePaged(list, 5)
  return (
    <Card>
      <CardHeader>
        <CardTitle>Known problems in the data</CardTitle>
        <CardDescription>Each problem, how many records it affects, and which investigations it weakens.</CardDescription>
      </CardHeader>
      <CardContent>
        {list.length === 0 ? (
          <Missing what="Data quality" />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Problem</TableHead>
                  <TableHead className="text-right">Records</TableHead>
                  <TableHead>Investigations it weakens</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paged.visible.map((r) => (
                  <TableRow key={r.problem}>
                    <TableCell className="max-w-80 whitespace-normal">
                      <p className="font-medium">{r.problem.charAt(0).toUpperCase() + r.problem.slice(1)}</p>
                      <p className="text-sm text-muted-foreground">{r.what}</p>
                    </TableCell>
                    <TableCell className="tnum text-right align-top">{count(r.affected_count)}</TableCell>
                    <TableCell className="align-top whitespace-normal text-sm text-muted-foreground">
                      {r.taints.length === 0 ? 'None' : r.taints.length >= 18 ? 'All 18' : r.taints.join(', ')}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Pager {...paged} />
          </>
        )}
      </CardContent>
    </Card>
  )
}
