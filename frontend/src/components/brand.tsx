import { Link } from 'react-router'
import { cn } from '@/lib/utils'

/** The mark: one red thread running through three knots, the way a case runs through its evidence. */
export function Mark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn('size-6', className)} aria-hidden="true">
      <path d="M3 22 C 9 22, 9 10, 16 10 S 23 22, 29 22" fill="none" stroke="var(--fraud)" strokeWidth="2.5" strokeLinecap="round" />
      <circle cx="3" cy="22" r="2.5" fill="currentColor" />
      <circle cx="16" cy="10" r="2.5" fill="currentColor" />
      <circle cx="29" cy="22" r="2.5" fill="currentColor" />
    </svg>
  )
}

export function Brand({ to = '/' }: { to?: string }) {
  return (
    <Link to={to} className="flex items-center gap-2 rounded-md font-semibold tracking-tight outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
      <Mark />
      <span className="hidden text-[1.05rem] sm:inline">RedThread</span>
    </Link>
  )
}
