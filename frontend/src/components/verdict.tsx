import type { Verdict } from '@/lib/api'
import { VERDICT_LABEL, prob } from '@/lib/format'
import { cn } from '@/lib/utils'

/* Fraud is the only verdict with a hue. Legitimate is teal and quiet; uncertain has no colour at all,
 * so it never competes with fraud for attention. */
const TONE: Record<Verdict, string> = {
  fraud: 'bg-fraud-soft text-fraud ring-fraud/25',
  legitimate: 'bg-cleared-soft text-cleared ring-cleared/25',
  uncertain: 'bg-muted text-muted-foreground ring-border',
}

export function VerdictBadge({ verdict, className }: { verdict?: Verdict | string | null; className?: string }) {
  if (!verdict || !(verdict in TONE)) {
    return <span className={cn('text-sm text-muted-foreground', className)}>Not investigated</span>
  }
  const v = verdict as Verdict
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset',
        TONE[v],
        className,
      )}
    >
      <span className={cn('size-1.5 rounded-full', v === 'fraud' ? 'bg-fraud' : v === 'legitimate' ? 'bg-cleared' : 'bg-muted-foreground/60')} />
      {VERDICT_LABEL[v]}
    </span>
  )
}

/** Probability of fraud as a number and a thin bar, with the decision thresholds marked. */
export function ProbabilityBar({ value, className }: { value?: number | null; className?: string }) {
  if (value == null) return <span className="text-sm text-muted-foreground">Not computed</span>
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <div className="relative h-1.5 w-20 overflow-hidden rounded-full bg-muted">
        <div
          className={cn('absolute inset-y-0 left-0 rounded-full', value >= 0.8 ? 'bg-fraud' : value <= 0.2 ? 'bg-cleared' : 'bg-muted-foreground/50')}
          style={{ width: `${Math.max(2, value * 100)}%` }}
        />
      </div>
      <span className="tnum text-sm">{prob(value)}</span>
    </div>
  )
}
