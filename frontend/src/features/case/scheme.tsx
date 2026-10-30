import { Id } from '@/components/states'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { ActivityShift, SchemePeers } from '@/lib/api'
import { date, money } from '@/lib/format'
import { cn } from '@/lib/utils'

/* The strongest evidence in the January cases: what this card had never done, and how many other
 * customers' cards started the same thing in the same 30 days, against the two windows before. */
export function SchemeFinding({ shift, peers }: { shift: ActivityShift; peers?: SchemePeers }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Something this card had never done</CardTitle>
        <CardDescription className="max-w-[72ch]">{sentence(shift.signature)}.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6 lg:grid-cols-2">
        <Run shift={shift} />
        {peers && <Peers peers={peers} />}
      </CardContent>
    </Card>
  )
}

export function Run({ shift }: { shift: ActivityShift }) {
  const times = shift.run.map((t) => new Date(t.ts.replace(' ', 'T')).getTime())
  const start = Math.min(...times)
  const end = Math.max(...times)
  const span = Math.max(1, end - start)
  const maxAmount = Math.max(...shift.run.map((t) => t.amount))
  const days = Math.round((end - start) / 86_400_000)

  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="text-sm font-medium">
          {shift.run.length} new charges, {money(shift.run_total_usd, true)}
        </h4>
        <span className="text-sm text-muted-foreground">{days < 1 ? 'within a day' : `over ${days} ${days === 1 ? 'day' : 'days'}`}</span>
      </div>
      <div className="relative h-28 rounded-lg border bg-muted/30 px-4" role="img" aria-label={`${shift.run.length} charges between ${date(shift.run[0]?.ts)} and ${date(shift.run.at(-1)?.ts)}`}>
        <div className="absolute inset-x-4 bottom-7 h-px bg-border" />
        {shift.run.map((t, i) => {
          const x = ((times[i] - start) / span) * 100
          const h = 12 + (t.amount / maxAmount) * 52
          return (
            <div key={t.tx_id} className="group absolute bottom-7 -translate-x-1/2" style={{ left: `calc(1rem + (100% - 2rem) * ${x / 100})` }}>
              <div className="w-1.5 rounded-t-sm bg-fraud" style={{ height: h }} />
              <span className="tnum pointer-events-none absolute -top-5 left-1/2 hidden -translate-x-1/2 text-xs whitespace-nowrap group-hover:block">
                {money(t.amount, true)}
              </span>
            </div>
          )
        })}
        <span className="absolute bottom-1.5 left-4 text-xs text-muted-foreground">{date(shift.run[0]?.ts)}</span>
        <span className="absolute right-4 bottom-1.5 text-xs text-muted-foreground">{date(shift.run.at(-1)?.ts)}</span>
      </div>
      <p className="text-sm text-muted-foreground">
        In the {shift.baseline_txns} charges before, the card was used {byChannel(shift.baseline_kinds)}.
      </p>
      <div className="flex flex-wrap gap-1">
        {shift.run.map((t) => (
          <Id key={t.tx_id}>{t.tx_id}</Id>
        ))}
      </div>
    </section>
  )
}

export function Peers({ peers }: { peers: SchemePeers }) {
  const windows = [
    { label: 'Two months before', n: peers.other_cards_two_months_before },
    { label: 'The month before', n: peers.other_cards_month_before },
    { label: 'The same 30 days', n: peers.other_cards_now, now: true },
  ]
  const max = Math.max(1, ...windows.map((w) => w.n))
  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="text-sm font-medium">{peers.other_cards_now} other cards started the same</h4>
        <span className="shrink-0 text-sm text-muted-foreground">{peers.strength} evidence</span>
      </div>
      <div className="space-y-2.5">
        {windows.map((w) => (
          <div key={w.label} className="grid grid-cols-[9rem_1fr_2.5rem] items-center gap-3 text-sm">
            <span className={cn('text-muted-foreground', w.now && 'font-medium text-foreground')}>{w.label}</span>
            <div className="h-5 rounded bg-muted">
              <div className={cn('h-full rounded', w.now ? 'bg-fraud' : 'bg-muted-foreground/35')} style={{ width: `${(w.n / max) * 100}%` }} />
            </div>
            <span className="tnum text-right font-medium">{w.n}</span>
          </div>
        ))}
      </div>
      {peers.peers.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-sm text-muted-foreground">The other cards</p>
          <div className="flex flex-wrap gap-1">
            {peers.peers.slice(0, 10).map((p) => (
              <Id key={p.card_id}>{p.card_id}</Id>
            ))}
            {peers.peers.length > 10 && <span className="text-sm text-muted-foreground">and {peers.peers.length - 10} more</span>}
          </div>
        </div>
      )}
    </section>
  )
}

/** Baseline kinds are product/channel pairs; an analyst reads them by channel. */
function byChannel(kinds: Record<string, number>) {
  const totals: Record<string, number> = {}
  for (const [k, n] of Object.entries(kinds)) {
    const channel = (k.split('/')[1] ?? k).replace('_', ' ')
    totals[channel] = (totals[channel] ?? 0) + n
  }
  return Object.entries(totals)
    .sort((a, b) => b[1] - a[1])
    .map(([c, n]) => `${n} ${n === 1 ? 'time' : 'times'} ${c}`)
    .join(' and ')
}

const sentence = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
