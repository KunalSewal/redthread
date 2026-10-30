import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, CircleDashed, XCircle } from 'lucide-react'
import { toast } from 'sonner'
import { SignInDialog } from '@/components/analyst-menu'
import { Empty, Id, Loading } from '@/components/states'
import { VerdictBadge } from '@/components/verdict'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { api, type CaseAction, type CaseDetail, type ChallengeRecord } from '@/lib/api'
import { useAnalyst } from '@/lib/analyst'
import { action, approvalLevel, dateTime, prob, sentence } from '@/lib/format'
import { keys, useChallenges } from '@/lib/queries'

const HARMFUL = new Set(['BLOCK_CARD', 'BLOCK_ALL_CARDS', 'FILE_REPORT'])
const words = (s: string) => s.trim().split(/\s+/).filter(Boolean).length

function useRefresh(caseId: string) {
  const qc = useQueryClient()
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: keys.case(caseId) }),
      qc.invalidateQueries({ queryKey: keys.cases }),
      qc.invalidateQueries({ queryKey: keys.overview }),
    ])
}

export function DecisionsTab({ detail }: { detail: CaseDetail }) {
  const caseId = detail.alert.case_id
  const challenges = useChallenges(caseId)
  const verdict = detail.answer!.case.verdict
  const standing = (challenges.data ?? []).some(
    (c) => c.position === 'legitimate' && (c.evaluation.status === 'accepted' || c.decision === 'upheld'),
  )

  const human = detail.actions.filter((a) => a.route !== 'auto')
  const auto = detail.actions.filter((a) => a.route === 'auto')

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Actions that need a person</CardTitle>
            <CardDescription>
              The agent recommends; only a person approves. Bigger stakes ask for a written reason.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {human.length === 0 ? (
              <Empty>Nothing here needs approval. The agent handled every action itself.</Empty>
            ) : (
              human.map((a) => (
                <ActionRow
                  key={a.action}
                  caseId={caseId}
                  item={a}
                  needsChallenge={verdict === 'fraud' && HARMFUL.has(a.action) && !standing}
                />
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Done by the agent</CardTitle>
            <CardDescription>Actions the policy lets it take on its own.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="divide-y">
              {auto.map((a) => (
                <li key={a.action} className="flex items-start justify-between gap-4 py-2.5 text-sm">
                  <div>
                    <p className="font-medium">{action(a.action)}</p>
                    <p className="text-muted-foreground">{a.reason}</p>
                  </div>
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-label="Done" />
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      <Challenges detail={detail} records={challenges.data} loading={challenges.isPending} />
    </div>
  )
}

function ActionRow({ caseId, item, needsChallenge }: { caseId: string; item: CaseAction; needsChallenge: boolean }) {
  const level = approvalLevel(item.route)
  const [deciding, setDeciding] = useState<'approved' | 'rejected' | null>(null)
  const decided = item.approval

  return (
    <div className="space-y-3 rounded-lg border p-4">
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium">{action(item.action)}</p>
            <Badge variant={item.route === 'L2' ? 'default' : 'secondary'}>{level.label}</Badge>
          </div>
          <p className="max-w-[70ch] text-sm text-muted-foreground">{item.reason}</p>
        </div>
        {decided ? (
          <span className="inline-flex items-center gap-1.5 text-sm font-medium">
            {decided.decision === 'approved' ? <CheckCircle2 className="size-4 text-cleared" /> : <XCircle className="size-4" />}
            {sentence(decided.decision)} by {decided.approver}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
            <CircleDashed className="size-4" /> Waiting on you
          </span>
        )}
      </div>

      {decided ? (
        <p className="text-sm text-muted-foreground">
          {dateTime(decided.at)}
          {decided.note && <>: “{decided.note}”</>}
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={() => setDeciding('approved')}>
            Approve
          </Button>
          <Button size="sm" variant="outline" onClick={() => setDeciding('rejected')}>
            Reject
          </Button>
          {needsChallenge && (
            <span className="text-sm text-muted-foreground">
              To reject this on a fraud verdict, first raise a challenge with evidence and have it accepted.
            </span>
          )}
        </div>
      )}
      <DecideDialog caseId={caseId} item={item} decision={deciding} onClose={() => setDeciding(null)} />
    </div>
  )
}

function DecideDialog({
  caseId,
  item,
  decision,
  onClose,
}: {
  caseId: string
  item: CaseAction
  decision: 'approved' | 'rejected' | null
  onClose: () => void
}) {
  const { analyst } = useAnalyst()
  const refresh = useRefresh(caseId)
  const [note, setNote] = useState('')
  const needsReason = approvalLevel(item.route).needsReason || decision === 'rejected'
  const decide = useMutation({
    mutationFn: () => api.approve(caseId, analyst!.key, { action: item.action, decision: decision!, note: note.trim() }),
    onSuccess: async () => {
      toast.success(`${action(item.action)}: ${decision}`)
      setNote('')
      onClose()
      await refresh()
    },
  })

  if (decision && !analyst)
    return <SignInDialog open onOpenChange={(o) => !o && onClose()} reason="Approving and rejecting are signed decisions." />

  const verb = decision === 'approved' ? 'Approve' : 'Reject'
  const ready = !needsReason || words(note) >= 5

  return (
    <Dialog open={!!decision} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault()
            decide.mutate()
          }}
        >
          <DialogHeader>
            <DialogTitle>
              {verb}: {action(item.action).toLowerCase()}
            </DialogTitle>
            <DialogDescription>
              Recorded against {analyst?.name} on <span className="font-mono">{caseId}</span>, and written onto the case in the graph.
              Decisions are final.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="decision-note">{needsReason ? 'Your reason (at least five words)' : 'Note (optional)'}</Label>
            <Textarea id="decision-note" value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
          </div>
          {decide.isError && <p className="text-sm text-destructive">{(decide.error as Error).message}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!ready || decide.isPending}>
              {decide.isPending ? 'Recording' : verb}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function Challenges({ detail, records, loading }: { detail: CaseDetail; records?: ChallengeRecord[]; loading: boolean }) {
  const caseId = detail.alert.case_id
  const verdict = detail.answer!.case.verdict
  const [open, setOpen] = useState(false)
  const list = records ?? []

  return (
    <Card className="self-start">
      <CardHeader>
        <CardTitle>Disagree with the verdict</CardTitle>
        <CardDescription>
          A challenge is weighed like any other evidence. It needs a reason and the IDs from this case it rests on. If the
          evidence does not settle it, a second analyst decides.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Button variant="outline" className="w-full" onClick={() => setOpen(true)}>
          Raise a challenge
        </Button>
        {loading ? (
          <Loading rows={2} />
        ) : list.length === 0 ? (
          <p className="text-sm text-muted-foreground">No one has challenged this case.</p>
        ) : (
          <ul className="space-y-3">
            {list.map((c) => (
              <ChallengeItem key={c.action} caseId={caseId} record={c} />
            ))}
          </ul>
        )}
      </CardContent>
      <RaiseDialog caseId={caseId} verdict={verdict} open={open} onClose={() => setOpen(false)} />
    </Card>
  )
}

const STATUS: Record<string, string> = {
  accepted: 'Accepted by the evidence',
  contested: 'Contested: waiting for a second analyst',
  rejected: 'Not supported by the evidence',
}

function ChallengeItem({ caseId, record, }: { caseId: string; record: ChallengeRecord }) {
  const [settling, setSettling] = useState<'upheld' | 'overruled' | null>(null)
  const e = record.evaluation
  const n = Number(record.action.replace('challenge-', ''))
  return (
    <li className="space-y-2 rounded-lg border p-3 text-sm">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2">
          Says <VerdictBadge verdict={record.position} />
        </span>
        <span className="text-xs text-muted-foreground">
          {record.by}, {dateTime(record.at)}
        </span>
      </div>
      <p className="leading-relaxed">{record.reason}</p>
      <p className="text-muted-foreground">
        {record.decision ? `${sentence(record.decision)} by a second analyst` : (STATUS[e.status] ?? e.status)}.{' '}
        Probability {prob(e.probability_before)} to {prob(e.probability_after)}.
      </p>
      {e.ids_not_in_case.length > 0 && (
        <p className="text-muted-foreground">
          Not part of this case: {e.ids_not_in_case.map((id) => <Id key={id} className="mr-1">{id}</Id>)}
        </p>
      )}
      {e.status === 'contested' && !record.decision && (
        <div className="flex gap-2 pt-1">
          <Button size="sm" onClick={() => setSettling('upheld')}>
            Uphold
          </Button>
          <Button size="sm" variant="outline" onClick={() => setSettling('overruled')}>
            Overrule
          </Button>
        </div>
      )}
      <SettleDialog caseId={caseId} n={n} decision={settling} onClose={() => setSettling(null)} />
    </li>
  )
}

function SettleDialog({ caseId, n, decision, onClose }: { caseId: string; n: number; decision: 'upheld' | 'overruled' | null; onClose: () => void }) {
  const { analyst } = useAnalyst()
  const qc = useQueryClient()
  const refresh = useRefresh(caseId)
  const [reason, setReason] = useState('')
  const settle = useMutation({
    mutationFn: () => api.settle(caseId, n, analyst!.key, { decision: decision!, reason: reason.trim() }),
    onSuccess: async () => {
      toast.success(`Challenge ${decision}`)
      onClose()
      await Promise.all([refresh(), qc.invalidateQueries({ queryKey: keys.challenges(caseId) })])
    },
  })
  if (decision && !analyst)
    return <SignInDialog open onOpenChange={(o) => !o && onClose()} reason="Settling a challenge is a signed decision." />
  return (
    <Dialog open={!!decision} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <form className="grid gap-4" onSubmit={(e) => (e.preventDefault(), settle.mutate())}>
          <DialogHeader>
            <DialogTitle>{decision === 'upheld' ? 'Uphold the challenge' : 'Overrule the challenge'}</DialogTitle>
            <DialogDescription>
              You are the second analyst. The person who raised a challenge cannot settle it.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="settle-reason">Your reason, one an auditor could check (at least five words)</Label>
            <Textarea id="settle-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={3} />
          </div>
          {settle.isError && <p className="text-sm text-destructive">{(settle.error as Error).message}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={words(reason) < 5 || settle.isPending}>
              {settle.isPending ? 'Recording' : decision === 'upheld' ? 'Uphold' : 'Overrule'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function RaiseDialog({ caseId, verdict, open, onClose }: { caseId: string; verdict: string; open: boolean; onClose: () => void }) {
  const { analyst } = useAnalyst()
  const qc = useQueryClient()
  const refresh = useRefresh(caseId)
  const positions = (['fraud', 'legitimate'] as const).filter((p) => p !== verdict)
  const [position, setPosition] = useState<string>(positions[0])
  const [reason, setReason] = useState('')
  const [ids, setIds] = useState('')
  const raise = useMutation({
    mutationFn: () =>
      api.challenge(caseId, analyst!.key, {
        position,
        reason: reason.trim(),
        evidence_ids: ids.split(/[\s,]+/).filter(Boolean),
      }),
    onSuccess: async (r) => {
      toast.success(STATUS[r.evaluation.status] ?? 'Challenge recorded')
      setReason('')
      setIds('')
      onClose()
      await Promise.all([refresh(), qc.invalidateQueries({ queryKey: keys.challenges(caseId) })])
    },
  })

  if (open && !analyst)
    return <SignInDialog open onOpenChange={(o) => !o && onClose()} reason="A challenge is recorded against the analyst who raises it." />

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <form className="grid gap-4" onSubmit={(e) => (e.preventDefault(), raise.mutate())}>
          <DialogHeader>
            <DialogTitle>Raise a challenge</DialogTitle>
            <DialogDescription>
              The agent concluded {verdict}. Say what you think and cite records from this case; a claim that cites nothing counts
              only as weak evidence.
            </DialogDescription>
          </DialogHeader>
          {positions.length > 1 && (
            <div className="flex gap-2" role="radiogroup" aria-label="Your position">
              {positions.map((p) => (
                <Button key={p} type="button" variant={position === p ? 'secondary' : 'outline'} aria-pressed={position === p} onClick={() => setPosition(p)}>
                  It is {p}
                </Button>
              ))}
            </div>
          )}
          <div className="grid gap-2">
            <Label htmlFor="challenge-reason">Why you think it is {position}</Label>
            <Textarea id="challenge-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={4} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="challenge-ids">IDs from this case it rests on</Label>
            <Input id="challenge-ids" value={ids} onChange={(e) => setIds(e.target.value)} placeholder="Transaction or card IDs, separated by commas" />
          </div>
          {raise.isError && <p className="text-sm text-destructive">{(raise.error as Error).message}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={words(reason) < 3 || raise.isPending}>
              {raise.isPending ? 'Weighing it' : 'Submit for weighing'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
