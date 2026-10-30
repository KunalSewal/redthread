import { useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'

/** Show a long list a page at a time. Returns the visible slice and the controls. */
export function usePaged<T>(items: T[], size: number) {
  const [page, setPage] = useState(0)
  const pages = Math.max(1, Math.ceil(items.length / size))
  const current = Math.min(page, pages - 1)
  return {
    visible: items.slice(current * size, current * size + size),
    page: current,
    pages,
    total: items.length,
    size,
    setPage,
  }
}

export function Pager({ page, pages, total, size, setPage }: ReturnType<typeof usePaged<unknown>>) {
  if (total <= size) return null
  const from = page * size + 1
  const to = Math.min(total, from + size - 1)
  return (
    <div className="flex items-center justify-between gap-3 pt-3">
      <span className="tnum text-sm text-muted-foreground">
        {from}–{to} of {total}
      </span>
      <div className="flex items-center gap-1">
        <Button variant="outline" size="sm" onClick={() => setPage(page - 1)} disabled={page === 0}>
          <ChevronLeft />
          Previous
        </Button>
        <Button variant="outline" size="sm" onClick={() => setPage(page + 1)} disabled={page >= pages - 1}>
          Next
          <ChevronRight />
        </Button>
      </div>
    </div>
  )
}
