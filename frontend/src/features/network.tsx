import { useState } from 'react'
import { Pager, usePaged } from '@/components/pager'
import { Empty, ErrorState, Id, Loading } from '@/components/states'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { ContainmentPlan, Ring } from '@/lib/api'
import { count, date, money, pct } from '@/lib/format'
import { useContainment, useRing, useRings } from '@/lib/queries'

export function NetworkPanel() {
  return (
    <div className="space-y-6">
      <ContainmentCard />
      <RingsCard />
    </div>
  )
}

function ContainmentCard() {
  const q = useContainment()
  const [open, setOpen] = useState<ContainmentPlan | null>(null)
  const plans = q.data?.plans ?? []
  const live = plans.filter((p) => p.plan.exposure_total_usd > 0)
  const paged = usePaged(plans, 6)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Containment plans</CardTitle>
        <CardDescription>
          For each fraud ring and January scheme, the blocks that stop the most money while touching the fewest legitimate
          customers.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {q.isPending ? (
          <Loading />
        ) : q.isError ? (
          <ErrorState error={q.error} title="No containment plans yet" />
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-3">
              <Figure
                label="Exposure stopped"
                value={money(sum(live, (p) => p.plan.exposure_cut_usd))}
                note={`of ${money(sum(live, (p) => p.plan.exposure_total_usd))} across ${live.length} rings and schemes`}
              />
              <Figure
                label="Customers the plans may touch"
                value={count(sum(live, (p) => p.plan.customers_touched.length))}
                note={`Blocking every card would touch ${count(sum(live, (p) => p.block_every_card.customers_touched.length))}`}
              />
              <Figure label="Planned as of" value={date(q.data.planned_as_of)} note={`Each wrongly touched customer counts as ${money(q.data.penalty_usd_per_person)} of harm`} />
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Ring or scheme</TableHead>
                  <TableHead className="text-right">Cards</TableHead>
                  <TableHead className="text-right">Blocks</TableHead>
                  <TableHead className="text-right">Stops</TableHead>
                  <TableHead className="text-right">Left</TableHead>
                  <TableHead className="text-right">Customers touched</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paged.visible.map((p) => (
                  <TableRow
                    key={p.ring}
                    className="cursor-pointer"
                    tabIndex={0}
                    onClick={() => setOpen(p)}
                    onKeyDown={(e) => e.key === 'Enter' && setOpen(p)}
                  >
                    <TableCell className="font-medium">{sentenceCase(p.ring)}</TableCell>
                    <TableCell className="tnum text-right">{p.cards.length}</TableCell>
                    <TableCell className="tnum text-right">{p.plan.actions.length}</TableCell>
                    <TableCell className="tnum text-right">{money(p.plan.exposure_cut_usd)}</TableCell>
                    <TableCell className="tnum text-right text-muted-foreground">{money(p.plan.exposure_left_usd)}</TableCell>
                    <TableCell className="tnum text-right">{p.plan.customers_touched.length}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Pager {...paged} />
          </>
        )}
      </CardContent>
      <PlanSheet plan={open} onClose={() => setOpen(null)} />
    </Card>
  )
}

function PlanSheet({ plan, onClose }: { plan: ContainmentPlan | null; onClose: () => void }) {
  return (
    <Sheet open={!!plan} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto data-[side=right]:sm:max-w-2xl">
        {plan && (
          <>
            <SheetHeader>
              <SheetTitle>{sentenceCase(plan.ring)}</SheetTitle>
              <SheetDescription>
                {plan.cards.length} cards and {plan.transactions} transactions
                {plan.shared.length > 0 && <>, linked through {plan.shared.join(', ')}</>}.
              </SheetDescription>
            </SheetHeader>
            <div className="space-y-6 px-4 pb-6">
              <div className="grid grid-cols-2 gap-4">
                <Figure label="This plan stops" value={money(plan.plan.exposure_cut_usd)} note={`of ${money(plan.plan.exposure_total_usd)}, touching ${plan.plan.customers_touched.length} customers`} />
                <Figure
                  label="Blocking every card"
                  value={money(plan.block_every_card.exposure_cut_usd)}
                  note={`touching ${plan.block_every_card.customers_touched.length} customers`}
                />
              </div>
              <section className="space-y-2">
                <h3 className="font-medium">What gets blocked</h3>
                <ul className="divide-y rounded-lg border">
                  {plan.plan.actions.map((a) => (
                    <li key={`${a.kind}-${a.target}`} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                      <span className="flex items-center gap-2">
                        <Badge variant="outline">{a.kind === 'card' ? 'Card' : a.kind === 'device' ? 'Device' : a.kind}</Badge>
                        <Id>{a.target}</Id>
                      </span>
                      <span className="tnum text-muted-foreground">
                        {money(a.cuts_usd, true)}
                        {a.kind === 'card' && plan.other_people_on_blocked_cards[a.target] != null &&
                          `, ${plan.other_people_on_blocked_cards[a.target]} other people use this card`}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
              {plan.monitor.length > 0 && (
                <section className="space-y-2">
                  <h3 className="font-medium">Watched, not blocked</h3>
                  <div className="flex flex-wrap gap-1.5">
                    {plan.monitor.map((c) => (
                      <Id key={c}>{c}</Id>
                    ))}
                  </div>
                </section>
              )}
              {plan.plan.customers_touched.length > 0 && (
                <section className="space-y-2">
                  <h3 className="font-medium">Customers this plan touches</h3>
                  <div className="flex flex-wrap gap-1.5">
                    {plan.plan.customers_touched.map((c) => (
                      <Id key={c}>{c}</Id>
                    ))}
                  </div>
                </section>
              )}
              <p className="text-sm text-muted-foreground">{plan.plan.method}</p>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}

function RingsCard() {
  const q = useRings()
  const [ringId, setRingId] = useState<number | null>(null)
  const paged = usePaged(q.data?.rings ?? [], 6)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Device rings</CardTitle>
        <CardDescription>Groups of cards tied together by specific devices they share, from the labelled history.</CardDescription>
      </CardHeader>
      <CardContent>
        {q.isPending ? (
          <Loading />
        ) : q.isError ? (
          <ErrorState error={q.error} title="No ring views yet" />
        ) : q.data.rings.length === 0 ? (
          <Empty>No rings were found.</Empty>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Ring</TableHead>
                  <TableHead className="text-right">Cards</TableHead>
                  <TableHead>Shared devices</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paged.visible.map((r) => (
                  <TableRow
                    key={r.ring_id}
                    className="cursor-pointer"
                    tabIndex={0}
                    onClick={() => setRingId(r.ring_id)}
                    onKeyDown={(e) => e.key === 'Enter' && setRingId(r.ring_id)}
                  >
                    <TableCell className="font-medium">Ring {r.ring_id}</TableCell>
                    <TableCell className="tnum text-right">{r.cards}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {r.devices.slice(0, 4).map((d) => (
                          <Id key={d}>{d}</Id>
                        ))}
                        {r.devices.length > 4 && <span className="text-sm text-muted-foreground">and {r.devices.length - 4} more</span>}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Pager {...paged} />
            <p className="pt-4 text-sm text-muted-foreground">
              Beyond the tight rings, the graph splits the cards into {count(q.data.communities_total)} wider communities.
            </p>
          </>
        )}
      </CardContent>
      <RingSheet ringId={ringId} onClose={() => setRingId(null)} />
    </Card>
  )
}

function RingSheet({ ringId, onClose }: { ringId: number | null; onClose: () => void }) {
  const q = useRing(ringId)
  const ring: Ring | undefined = q.data
  const members = usePaged(ring?.members ?? [], 8)
  return (
    <Sheet open={ringId != null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto data-[side=right]:sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle>Ring {ringId}</SheetTitle>
          <SheetDescription>{ring ? `${ring.cards} cards sharing ${ring.devices.length} ${ring.devices.length === 1 ? 'device' : 'devices'}` : 'Loading the ring'}</SheetDescription>
        </SheetHeader>
        <div className="space-y-6 px-4 pb-6">
          {q.isPending ? (
            <Loading />
          ) : q.isError ? (
            <ErrorState error={q.error} />
          ) : (
            <>
              {ring?.device_profiles && ring.device_profiles.length > 0 && (
                <section className="space-y-2">
                  <h3 className="font-medium">Devices</h3>
                  <ul className="divide-y rounded-lg border">
                    {ring.device_profiles.map((d) => (
                      <li key={d.device_id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                        <span className="flex items-center gap-2">
                          <Id>{d.device_id}</Id>
                          <span className="text-muted-foreground">{d.profile}</span>
                        </span>
                        <span className="tnum text-muted-foreground">{d.n_cards} cards</span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
              <section className="space-y-2">
                <h3 className="font-medium">Cards</h3>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Card</TableHead>
                      <TableHead className="text-right">Transactions</TableHead>
                      <TableHead className="text-right">Highest model score</TableHead>
                      <TableHead>Confirmed fraud cases</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {members.visible.map((m) => (
                      <TableRow key={m.card_id}>
                        <TableCell>
                          <Id>{m.card_id}</Id>
                        </TableCell>
                        <TableCell className="tnum text-right">{m.txns}</TableCell>
                        <TableCell className="tnum text-right">{m.max_model_score == null ? 'None' : pct(m.max_model_score)}</TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {m.confirmed_fraud_closed_cases.length ? m.confirmed_fraud_closed_cases.join(', ') : 'None'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <Pager {...members} />
              </section>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}

export function Figure({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="space-y-1 rounded-lg border bg-muted/30 p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="tnum text-2xl font-semibold tracking-tight">{value}</p>
      {note && <p className="text-sm text-muted-foreground">{note}</p>}
    </div>
  )
}

const sum = <T,>(xs: T[], f: (x: T) => number) => xs.reduce((a, x) => a + f(x), 0)
const sentenceCase = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
