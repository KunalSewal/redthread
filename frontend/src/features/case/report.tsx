import { FileCheck2, FileX2 } from 'lucide-react'
import { Id } from '@/components/states'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { CaseDetail } from '@/lib/api'
import { count, date, money } from '@/lib/format'

export function ReportTab({ detail }: { detail: CaseDetail }) {
  const a = detail.answer!
  const sar = a.sar

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {sar.file ? <FileCheck2 className="size-5" /> : <FileX2 className="size-5 text-muted-foreground" />}
            {sar.file ? 'Suspicious activity report' : 'No report to file'}
          </CardTitle>
          <CardDescription>{sar.reason}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {sar.file ? (
            <>
              <div className="grid gap-4 sm:grid-cols-3">
                <Item label="Total amount">{money(sar.total_amount_usd, true)}</Item>
                <Item label="Activity dates">
                  {sar.activity_dates.length ? `${date(sar.activity_dates[0])} to ${date(sar.activity_dates.at(-1))}` : 'None'}
                </Item>
                <Item label="Subjects">
                  <span className="flex flex-wrap items-center gap-1">
                    {sar.subjects.slice(0, 6).map((s) => (
                      <Id key={s}>{s}</Id>
                    ))}
                    {sar.subjects.length > 6 && (
                      <span className="text-sm font-normal text-muted-foreground">and {sar.subjects.length - 6} more</span>
                    )}
                  </span>
                </Item>
              </div>
              <div className="max-w-[72ch] space-y-3 leading-relaxed">
                {sar.narrative.split(/\n+/).map((p, i) => (
                  <p key={i}>{p}</p>
                ))}
              </div>
            </>
          ) : (
            <p className="text-muted-foreground">The policy does not call for a regulatory filing on this case.</p>
          )}
        </CardContent>
      </Card>

      <Card className="self-start">
        <CardHeader>
          <CardTitle>Why it stopped</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <p className="leading-relaxed">{a.stop_reason}</p>
          <div className="grid grid-cols-3 gap-2 border-t pt-4">
            <Item label="Queries">{count(a.tool_calls)}</Item>
            <Item label="Minutes">{(a.latency_s / 60).toFixed(1)}</Item>
            <Item label="Tokens">{count(a.tokens)}</Item>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <p className="text-sm text-muted-foreground">{label}</p>
      <div className="tnum font-medium">{children}</div>
    </div>
  )
}
