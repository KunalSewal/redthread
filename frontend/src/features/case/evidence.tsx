import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, RotateCcw } from 'lucide-react'
import { Pager, usePaged } from '@/components/pager'
import { Id } from '@/components/states'
import { ProbabilityBar, VerdictBadge } from '@/components/verdict'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { api, type CaseDetail, type LedgerItem } from '@/lib/api'
import { action, basis, prob } from '@/lib/format'
import { cn } from '@/lib/utils'

export function EvidenceTab({ detail }: { detail: CaseDetail }) {
  return (
    <div className="space-y-6">
      {detail.belief ? <Ledger detail={detail} /> : null}
      <Claims detail={detail} />
    </div>
  )
}

function whyNotCounted(l: LedgerItem) {
  if (l.as_prior) return 'Already set the starting point'
  if (l.uninformative) return 'From a month the model never saw'
  return 'A stronger line covers the same fact'
}

function Ledger({ detail }: { detail: CaseDetail }) {
  const b = detail.belief!
  const caseId = detail.alert.case_id
  const [dropped, setDropped] = useState<Set<number>>(new Set())
  const whatIf = useMutation({ mutationFn: (d: number[]) => api.counterfactual(caseId, d) })

  function toggle(i: number) {
    const next = new Set(dropped)
    if (next.has(i)) next.delete(i)
    else next.add(i)
    setDropped(next)
    whatIf.reset()
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>How the probability was built</CardTitle>
        <CardDescription className="max-w-[80ch]">
          The agent judges each finding; code turns those judgements into the probability. Untick a line to see what it would
          have concluded without it.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg bg-muted/40 px-4 py-3 text-sm">
          <span>
            Starting point <strong className="tnum">{prob(b.prior)}</strong>
            <span className="text-muted-foreground">, because {b.prior_reason}</span>
          </span>
          <span className="flex items-center gap-2">
            Final <ProbabilityBar value={b.posterior} />
          </span>
          <span className="text-muted-foreground">{b.independent_evidence} independent pieces of evidence</span>
        </div>

        <ul className="divide-y rounded-lg border">
          {b.ledger.map((l, i) => {
            const off = dropped.has(i)
            const up = l.direction === 'incriminating'
            return (
              <li key={i} className={cn('grid grid-cols-[auto_1fr_auto] gap-x-3 gap-y-1 px-4 py-3', off && 'opacity-50')}>
                <Checkbox
                  checked={!off}
                  onCheckedChange={() => toggle(i)}
                  aria-label={`Include: ${basis(l.basis)}`}
                  className="mt-0.5"
                />
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span
                      className={cn(
                        'inline-flex items-center gap-1 font-medium',
                        up ? 'text-fraud' : 'text-cleared',
                      )}
                    >
                      {up ? <ArrowUp className="size-3.5" /> : <ArrowDown className="size-3.5" />}
                      {basis(l.basis)}
                    </span>
                    <Badge variant="outline">{l.strength}</Badge>
                    {!l.counted && <span className="text-xs text-muted-foreground">Not counted: {whyNotCounted(l).toLowerCase()}</span>}
                  </div>
                  <p className="max-w-[90ch] text-sm leading-relaxed text-foreground/85">{l.claim}</p>
                </div>
                <span className="tnum self-start text-right text-sm text-muted-foreground" title="What it multiplied the odds by">
                  {l.counted ? `×${l.lr.toFixed(2)}` : 'none'}
                </span>
              </li>
            )
          })}
        </ul>

        <div className="flex flex-wrap items-center gap-2">
          <Button disabled={dropped.size === 0 || whatIf.isPending} onClick={() => whatIf.mutate([...dropped])}>
            {whatIf.isPending ? 'Recomputing' : `Recompute without ${dropped.size || 'the unticked'} ${dropped.size === 1 ? 'line' : 'lines'}`}
          </Button>
          {dropped.size > 0 && (
            <Button
              variant="ghost"
              onClick={() => {
                setDropped(new Set())
                whatIf.reset()
              }}
            >
              <RotateCcw />
              Put every line back
            </Button>
          )}
        </div>

        {whatIf.isError && <p className="text-sm text-destructive">{(whatIf.error as Error).message}</p>}
        {whatIf.data && (
          <div className="space-y-2 rounded-lg border p-4">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-sm text-muted-foreground">Without those lines it would conclude</span>
              <VerdictBadge verdict={whatIf.data.verdict} />
              <ProbabilityBar value={whatIf.data.posterior} />
            </div>
            {whatIf.data.actions.length > 0 && (
              <p className="text-sm">
                and recommend: {whatIf.data.actions.map((a) => action(a.action).toLowerCase()).join(', ')}.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function Claims({ detail }: { detail: CaseDetail }) {
  const ev = detail.answer?.case.evidence ?? []
  const paged = usePaged(ev, 6)
  return (
    <Card>
      <CardHeader>
        <CardTitle>Every claim, and where it came from</CardTitle>
        <CardDescription>Each claim names the query that produced it and the records it rests on.</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="divide-y">
          {paged.visible.map((e, i) => (
            <li key={i} className="space-y-1.5 py-3">
              <p className="max-w-[90ch] text-sm leading-relaxed">{e.claim}</p>
              <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                <span>{e.ref}</span>
                {e.entity_ids.slice(0, 8).map((id) => (
                  <Id key={id}>{id}</Id>
                ))}
                {e.entity_ids.length > 8 && <span>and {e.entity_ids.length - 8} more</span>}
              </div>
            </li>
          ))}
        </ul>
        <Pager {...paged} />
      </CardContent>
    </Card>
  )
}
