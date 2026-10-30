import { Id } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { SchemeFinding } from '@/features/case/scheme'
import { schemeEvidence, type ActionItem, type CaseDetail } from '@/lib/api'
import { action, approvalLevel, sentence } from '@/lib/format'
import { cn } from '@/lib/utils'

export function SummaryTab({ detail, onOpenDecisions }: { detail: CaseDetail; onOpenDecisions: () => void }) {
  const a = detail.answer!
  const c = a.case
  const h = detail.handover
  const { shift, peers } = schemeEvidence(detail)

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
      <div className="min-w-0 space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>What the agent concluded</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="max-w-[72ch] leading-relaxed">{c.summary}</p>
            {c.pattern === 'undocumented' && c.pattern_description && (
              <div className="max-w-[72ch] rounded-lg border-l-2 border-fraud bg-fraud-soft/50 px-4 py-3 text-sm">
                <p className="mb-1 font-medium">A scheme the policy does not name</p>
                <p className="leading-relaxed text-foreground/85">{c.pattern_description}</p>
              </div>
            )}
          </CardContent>
        </Card>

        {shift && <SchemeFinding shift={shift} peers={peers} />}

        <Card>
          <CardHeader>
            <CardTitle>The plan</CardTitle>
            <CardDescription>
              {a.next_best_actions.what_changed && a.next_best_actions.what_changed !== 'nothing'
                ? a.next_best_actions.what_changed
                : 'The recommendation did not change during the investigation.'}
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <Plan title="First recommendation" items={a.next_best_actions.initial} muted />
            <Plan title="Final recommendation" items={a.next_best_actions.final} />
          </CardContent>
        </Card>

        {a.evidence_requests.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>More evidence it asked for</CardTitle>
              <CardDescription>Replies are simulated in this round; the agent states what it assumed.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {a.evidence_requests.map((r, i) => (
                <div key={i} className="rounded-lg border p-3 text-sm">
                  <p className="font-medium">{sentence(r.type.replaceAll('_', ' '))}, after step {r.asked_after_step}</p>
                  <p className="mt-1 text-muted-foreground">{r.assumed_response}</p>
                </div>
              ))}
            </CardContent>
          </Card>
        )}
      </div>

      <aside className="space-y-6">
        {h && (
          <Card>
            <CardHeader>
              <CardTitle>Where it stands</CardTitle>
              <CardDescription>For whoever picks this case up next.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div>
                <p className="text-muted-foreground">Next step</p>
                <p className="mt-0.5 font-medium">{plainNextStep(h.next_step, h.waiting.length)}</p>
              </div>
              {h.waiting.length > 0 && (
                <div className="space-y-2">
                  <p className="text-muted-foreground">Waiting on you</p>
                  <ul className="space-y-1.5">
                    {h.waiting.map((w) => (
                      <li key={w.action} className="flex items-center justify-between gap-2">
                        <span>{action(w.action)}</span>
                        <span className="text-xs text-muted-foreground">{approvalLevel(w.needs as 'L1').label}</span>
                      </li>
                    ))}
                  </ul>
                  <Button size="sm" className="w-full" onClick={onOpenDecisions}>
                    Review the decisions
                  </Button>
                </div>
              )}
              {h.contested_challenges.length > 0 && (
                <div>
                  <p className="text-muted-foreground">Contested challenges</p>
                  <p className="mt-0.5">{h.contested_challenges.length} waiting for a second analyst</p>
                </div>
              )}
              {h.open_question && (
                <div>
                  <p className="text-muted-foreground">Still open</p>
                  <p className="mt-0.5 leading-relaxed">{h.open_question}</p>
                </div>
              )}
              {h.in_graph && (
                <p className="text-muted-foreground">
                  Saved in the graph as <Id>{h.in_graph}</Id>
                </p>
              )}
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader>
            <CardTitle>What it touches</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <IdGroup label="Affected transactions" ids={c.affected_txn_ids} />
            <IdGroup label="Connected cards" ids={c.connected_card_ids} />
            <IdGroup label="Shared devices" ids={c.connected_device_profiles} />
            <IdGroup label="Similar past cases" ids={c.similar_prior_cases} />
          </CardContent>
        </Card>
      </aside>
    </div>
  )
}

function Plan({ title, items, muted }: { title: string; items: ActionItem[]; muted?: boolean }) {
  return (
    <div className={cn('space-y-2', muted && 'text-muted-foreground')}>
      <p className="text-sm font-medium">{title}</p>
      <ol className="space-y-1.5">
        {items.map((it) => (
          <li key={it.action} className="flex items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm">
            <span>{action(it.action)}</span>
            <span className="shrink-0 text-xs text-muted-foreground">{approvalLevel(it.route).label}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}

function IdGroup({ label, ids }: { label: string; ids: string[] }) {
  const shown = ids.slice(0, 12)
  return (
    <div className="space-y-1.5">
      <p className="text-sm text-muted-foreground">
        {label} <span className="tnum">({ids.length})</span>
      </p>
      {ids.length === 0 ? (
        <p className="text-sm">None</p>
      ) : (
        <div className="flex flex-wrap gap-1">
          {shown.map((id) => (
            <Id key={id}>{id}</Id>
          ))}
          {ids.length > shown.length && <span className="text-sm text-muted-foreground">and {ids.length - shown.length} more</span>}
        </div>
      )}
    </div>
  )
}

/** The backend names roles ("an L1 approver decides BLOCK_CARD"); with one analyst role, say it plainly. */
function plainNextStep(text: string, waiting: number) {
  if (waiting > 0) return `You decide ${waiting === 1 ? 'one recommended action' : `${waiting} recommended actions`}.`
  return sentence(text.replace(/an L[12] approver/g, 'an analyst'))
}
