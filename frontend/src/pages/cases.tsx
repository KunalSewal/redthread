import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router'
import { Search } from 'lucide-react'
import { Pager, usePaged } from '@/components/pager'
import { Empty, ErrorState, Loading } from '@/components/states'
import { VerdictBadge } from '@/components/verdict'
import { Input } from '@/components/ui/input'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { CaseView } from '@/features/case/case-view'
import type { CaseRow } from '@/lib/api'
import { isBankQueue, money, pattern, trigger } from '@/lib/format'
import { useCases } from '@/lib/queries'
import { cn } from '@/lib/utils'

const PAGE = 10
type Source = 'all' | 'bank' | 'agent'
type VerdictFilter = 'all' | 'fraud' | 'uncertain' | 'legitimate' | 'waiting'

export function CasesPage() {
  const { caseId } = useParams()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const cases = useCases()

  const source = (params.get('source') as Source) || 'all'
  const verdict: VerdictFilter = params.get('waiting') ? 'waiting' : (params.get('verdict') as VerdictFilter) || 'all'
  const [query, setQuery] = useState('')

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    // The bank's own queue leads; the alerts the agent raised itself follow.
    const rows = [...(cases.data ?? [])].sort(
      (a, b) => Number(!isBankQueue(a.source)) - Number(!isBankQueue(b.source)) || a.case_id.localeCompare(b.case_id),
    )
    return rows.filter(
      (c) =>
        (source === 'all' || (source === 'bank') === isBankQueue(c.source)) &&
        (verdict === 'all' || (verdict === 'waiting' ? (c.pending_approvals ?? 0) > 0 : c.verdict === verdict)) &&
        (!q || [c.case_id, c.card_id, c.customer_id, c.flagged_txn_id].some((v) => v?.toLowerCase().includes(q))),
    )
  }, [cases.data, source, verdict, query])

  const paged = usePaged(filtered, PAGE)
  const { setPage } = paged

  // A new filter starts from the first page.
  useEffect(() => setPage(0), [source, verdict, query, setPage])

  // Open the first case when none is chosen, so the workspace is never empty on a wide screen.
  useEffect(() => {
    if (!caseId && filtered.length > 0 && window.matchMedia('(min-width: 1024px)').matches) {
      navigate(`/app/cases/${filtered[0].case_id}?${params.toString()}`, { replace: true })
    }
  }, [caseId, filtered, navigate, params])

  function setFilter(key: 'source' | 'verdict', value: string) {
    const next = new URLSearchParams(params)
    next.delete('waiting')
    if (value === 'all') next.delete(key)
    else if (key === 'verdict' && value === 'waiting') {
      next.delete('verdict')
      next.set('waiting', '1')
    } else next.set(key, value)
    setParams(next, { replace: true })
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[340px_minmax(0,1fr)] xl:gap-8">
      <aside className={cn('space-y-3 lg:self-start', caseId && 'hidden lg:block')} aria-label="Case list">
        <div className="flex items-baseline justify-between">
          <h1 className="text-xl font-semibold tracking-tight">Cases</h1>
          {cases.data && <span className="tnum text-sm text-muted-foreground">{filtered.length} shown</span>}
        </div>
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Find a case, card, customer or transaction"
            className="pl-8"
            aria-label="Find a case"
          />
        </div>
        <Tabs value={source} onValueChange={(v) => setFilter('source', String(v))}>
          <TabsList className="w-full">
            <TabsTrigger value="all">All</TabsTrigger>
            <TabsTrigger value="bank">Bank queue</TabsTrigger>
            <TabsTrigger value="agent">Raised by agent</TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by verdict">
          {(['all', 'waiting', 'fraud', 'uncertain', 'legitimate'] as VerdictFilter[]).map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setFilter('verdict', v)}
              aria-pressed={verdict === v}
              className={cn(
                'rounded-full border px-2.5 py-1 text-xs font-medium transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50',
                verdict === v ? 'border-foreground bg-foreground text-background' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {v === 'all' ? 'Any verdict' : v === 'waiting' ? 'Waiting on you' : v.charAt(0).toUpperCase() + v.slice(1)}
            </button>
          ))}
        </div>

        {cases.isPending ? (
          <Loading rows={8} />
        ) : cases.isError ? (
          <ErrorState error={cases.error} />
        ) : filtered.length === 0 ? (
          <Empty>No case matches. Clear the search or pick another filter.</Empty>
        ) : (
          <>
            <ul className="divide-y overflow-hidden rounded-xl border bg-card">
              {paged.visible.map((c) => (
                <CaseListItem
                  key={c.case_id}
                  row={c}
                  active={c.case_id === caseId}
                  onOpen={() => navigate(`/app/cases/${c.case_id}?${params.toString()}`)}
                />
              ))}
            </ul>
            <Pager {...paged} />
          </>
        )}
      </aside>

      {/* The open case sits on its own stage, so it reads apart from the list beside it. */}
      <section
        className={cn(
          'min-w-0 lg:rounded-2xl lg:bg-stage lg:p-6 lg:ring-1 lg:ring-border',
          !caseId && 'hidden lg:block',
        )}
      >
        {caseId ? <CaseView caseId={caseId} onBack={() => navigate(`/app/cases?${params.toString()}`)} /> : <Empty>Pick a case from the list.</Empty>}
      </section>
    </div>
  )
}

function CaseListItem({ row, active, onOpen }: { row: CaseRow; active: boolean; onOpen: () => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        aria-current={active ? 'true' : undefined}
        className={cn(
          'relative block w-full px-4 py-3 text-left transition-colors outline-none hover:bg-muted/50 focus-visible:bg-muted/60',
          active && 'bg-muted',
        )}
      >
        {active && <span className="absolute inset-y-0 left-0 w-0.5 bg-foreground" aria-hidden="true" />}
        <span className="flex items-center justify-between gap-2">
          <span className="font-mono text-sm font-medium">{row.case_id}</span>
          <VerdictBadge verdict={row.verdict} />
        </span>
        <span className="mt-1 flex items-center justify-between gap-2 text-sm text-muted-foreground">
          <span className="truncate">
            {trigger(row.trigger_type)}, {pattern(row.pattern).toLowerCase()}
          </span>
          <span className="tnum shrink-0">{money(row.exposure_usd, true)}</span>
        </span>
        {(row.pending_approvals ?? 0) > 0 && (
          <span className="mt-1.5 inline-block text-xs font-medium text-foreground">
            {row.pending_approvals} {row.pending_approvals === 1 ? 'decision' : 'decisions'} waiting on you
          </span>
        )}
      </button>
    </li>
  )
}
