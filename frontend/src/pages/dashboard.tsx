import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { ArrowUpRight, LayoutGrid, Network, ShieldCheck } from 'lucide-react'
import { Pager, usePaged } from '@/components/pager'
import { Empty, ErrorState, Id, Loading } from '@/components/states'
import { ProbabilityBar, VerdictBadge } from '@/components/verdict'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { NetworkPanel } from '@/features/network'
import { TrustPanel } from '@/features/trust'
import type { CaseRow, Verdict } from '@/lib/api'
import { count, isBankQueue, money, pattern } from '@/lib/format'
import { useCases, useOverview } from '@/lib/queries'
import { cn } from '@/lib/utils'

const TABS = ['overview', 'network', 'trust'] as const
type Tab = (typeof TABS)[number]

const SECTIONS: { value: Tab; icon: typeof LayoutGrid; title: string; note: string }[] = [
  { value: 'overview', icon: LayoutGrid, title: 'Overview', note: 'Cases, verdicts and the decisions waiting on you' },
  { value: 'network', icon: Network, title: 'Fraud networks', note: 'Device rings and the plans to contain them' },
  { value: 'trust', icon: ShieldCheck, title: 'Assurance', note: 'Accuracy, failure drills and safeguards' },
]

export function DashboardPage() {
  const [params, setParams] = useSearchParams()
  const tab: Tab = TABS.includes(params.get('tab') as Tab) ? (params.get('tab') as Tab) : 'overview'

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground">Everything in front of the team, and what is waiting on you.</p>
        </div>
        <Button variant="outline" render={<Link to="/app/cases" />}>
          Open the case list
        </Button>
      </div>

      <Tabs value={tab} onValueChange={(v) => setParams(v === 'overview' ? {} : { tab: String(v) })}>
        <TabsList className="grid h-auto! w-full grid-cols-1 gap-3 bg-transparent p-0 sm:grid-cols-3">
          {SECTIONS.map(({ value, icon: Icon, title, note }) => (
            <TabsTrigger
              key={value}
              value={value}
              className="h-auto! items-start justify-start gap-3 rounded-xl border border-border bg-card px-4 py-3.5 text-left whitespace-normal text-muted-foreground shadow-none hover:bg-muted/40 data-active:border-foreground/70 data-active:bg-card data-active:text-foreground data-active:shadow-sm"
            >
              <Icon className="mt-0.5 size-5! shrink-0" />
              <span className="space-y-0.5">
                <span className="block text-[0.95rem] font-semibold">{title}</span>
                <span className="block text-sm font-normal text-muted-foreground">{note}</span>
              </span>
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="overview" className="pt-6">
          <Overview />
        </TabsContent>
        <TabsContent value="network" className="pt-6">
          <NetworkPanel />
        </TabsContent>
        <TabsContent value="trust" className="pt-6">
          <TrustPanel />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function Overview() {
  const overview = useOverview()
  const cases = useCases()

  if (overview.isPending || cases.isPending) return <Loading rows={6} />
  if (overview.isError) return <ErrorState error={overview.error} />
  if (cases.isError) return <ErrorState error={cases.error} />

  const o = overview.data
  const rows = cases.data
  const bank = rows.filter((c) => isBankQueue(c.source))
  const raised = rows.length - bank.length
  const waitingCases = rows.filter((c) => (c.pending_approvals ?? 0) > 0)

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Cases" value={count(o.cases)} note={`${bank.length} from the bank's queue, ${raised} raised by the agent`} />
        <Stat
          label="Decisions waiting on you"
          value={count(o.pending_approvals)}
          note={`Across ${waitingCases.length} cases`}
          to="/app/cases?waiting=1"
        />
        <Stat label="Money at risk" value={money(o.exposure_usd)} note="Exposure across every investigated case" />
        <Stat label="Reports to file" value={count(o.sars)} note="Suspicious activity reports the policy calls for" />
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="relative xl:col-span-2">
          <NeedsDecision rows={waitingCases} className="xl:absolute xl:inset-0" />
        </div>
        <div className="space-y-6">
          <VerdictSplit rows={rows} />
          <Patterns byPattern={o.by_pattern} />
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value, note, to }: { label: string; value: string; note: string; to?: string }) {
  const body = (
    <Card className={cn('h-full gap-1 py-5', to && 'transition-colors hover:bg-muted/40')}>
      <CardContent className="space-y-1.5">
        <p className="flex items-center justify-between text-sm text-muted-foreground">
          {label}
          {to && <ArrowUpRight className="size-4" aria-hidden="true" />}
        </p>
        <p className="tnum text-3xl font-semibold tracking-tight">{value}</p>
        <p className="text-sm text-muted-foreground">{note}</p>
      </CardContent>
    </Card>
  )
  return to ? (
    <Link to={to} className="rounded-xl outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
      {body}
    </Link>
  ) : (
    body
  )
}

function NeedsDecision({ rows, className }: { rows: CaseRow[]; className?: string }) {
  const navigate = useNavigate()
  const sorted = useMemo(() => [...rows].sort((a, b) => (b.exposure_usd ?? 0) - (a.exposure_usd ?? 0)), [rows])
  const [size, setSize] = useState(6)
  const paged = usePaged(sorted, size)
  const box = useRef<HTMLDivElement>(null)

  // On a wide screen the card is as tall as the column beside it; show as many rows as fit.
  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    const fit = () => {
      if (!window.matchMedia('(min-width: 1280px)').matches) return setSize(6)
      const head = el.querySelector('thead')?.getBoundingClientRect().height ?? 40
      const row = el.querySelector('tbody tr')?.getBoundingClientRect().height ?? 40
      setSize(Math.max(3, Math.floor((el.clientHeight - head) / row)))
    }
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  return (
    <Card className={cn('flex flex-col', className)}>
      <CardHeader>
        <CardTitle>Needs your decision</CardTitle>
        <CardDescription>Cases where the agent recommends an action only a person can approve, largest exposure first.</CardDescription>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col">
        {sorted.length === 0 ? (
          <Empty>Nothing is waiting on you.</Empty>
        ) : (
          <>
            <div ref={box} className="min-h-0 flex-1 overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Case</TableHead>
                    <TableHead>Verdict</TableHead>
                    <TableHead>Probability</TableHead>
                    <TableHead className="hidden md:table-cell">Pattern</TableHead>
                    <TableHead className="text-right">Waiting</TableHead>
                    <TableHead className="text-right">Exposure</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {paged.visible.map((c) => (
                    <TableRow
                      key={c.case_id}
                      className="cursor-pointer"
                      tabIndex={0}
                      onClick={() => navigate(`/app/cases/${c.case_id}`)}
                      onKeyDown={(e) => e.key === 'Enter' && navigate(`/app/cases/${c.case_id}`)}
                    >
                      <TableCell>
                        <Id>{c.case_id}</Id>
                      </TableCell>
                      <TableCell>
                        <VerdictBadge verdict={c.verdict} />
                      </TableCell>
                      <TableCell>
                        <ProbabilityBar value={c.fraud_probability} />
                      </TableCell>
                      <TableCell className="hidden text-muted-foreground md:table-cell">{pattern(c.pattern)}</TableCell>
                      <TableCell className="tnum text-right">{c.pending_approvals}</TableCell>
                      <TableCell className="tnum text-right font-medium">{money(c.exposure_usd, true)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <Pager {...paged} />
          </>
        )}
      </CardContent>
    </Card>
  )
}

const ORDER: Verdict[] = ['fraud', 'uncertain', 'legitimate']
const BAR: Record<Verdict, string> = { fraud: 'bg-fraud', uncertain: 'bg-muted-foreground/40', legitimate: 'bg-cleared' }

function VerdictSplit({ rows }: { rows: CaseRow[] }) {
  const groups = [
    { label: "Bank's queue", rows: rows.filter((c) => isBankQueue(c.source)) },
    { label: 'Raised by the agent', rows: rows.filter((c) => !isBankQueue(c.source)) },
  ]
  return (
    <Card>
      <CardHeader>
        <CardTitle>Verdicts</CardTitle>
        <CardDescription>What the agent concluded, by where the alert came from.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {groups.map((g) => {
          const n = g.rows.length
          const by = Object.fromEntries(ORDER.map((v) => [v, g.rows.filter((c) => c.verdict === v).length])) as Record<Verdict, number>
          return (
            <div key={g.label} className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="font-medium">{g.label}</span>
                <span className="tnum text-muted-foreground">{n} cases</span>
              </div>
              <div className="flex h-2.5 overflow-hidden rounded-full bg-muted" role="img" aria-label={ORDER.map((v) => `${by[v]} ${v}`).join(', ')}>
                {ORDER.map((v) => by[v] > 0 && <div key={v} className={BAR[v]} style={{ width: `${(by[v] / n) * 100}%` }} />)}
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                {ORDER.map((v) => (
                  <span key={v} className="flex items-center gap-1.5 text-muted-foreground">
                    <span className={cn('size-2 rounded-full', BAR[v])} />
                    <span className="tnum text-foreground">{by[v]}</span> {v}
                  </span>
                ))}
              </div>
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}

function Patterns({ byPattern }: { byPattern: Record<string, number> }) {
  const entries = Object.entries(byPattern).sort((a, b) => b[1] - a[1])
  const max = Math.max(1, ...entries.map(([, n]) => n))
  return (
    <Card>
      <CardHeader>
        <CardTitle>Patterns</CardTitle>
        <CardDescription>The kind of fraud each case fits. Undocumented means it fits none the policy names.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2.5">
        {entries.map(([p, n]) => (
          <div key={p} className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1">
            <span className="text-sm">{pattern(p)}</span>
            <span className="tnum text-sm text-muted-foreground">{n}</span>
            <div className="col-span-2 h-1.5 rounded-full bg-muted">
              <div className="h-full rounded-full bg-foreground/70" style={{ width: `${(n / max) * 100}%` }} />
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
