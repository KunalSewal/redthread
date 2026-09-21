/* A router in fifty lines, because five routes do not justify a dependency.
   Patterns are '/case/:id' style; a trailing ':param?' is optional. */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

interface RouteState {
  path: string
  params: Record<string, string>
  query: URLSearchParams
  navigate: (to: string, opts?: { replace?: boolean }) => void
}

const RouterContext = createContext<RouteState | null>(null)

function match(pattern: string, path: string): Record<string, string> | null {
  const p = pattern.split('/').filter(Boolean)
  const s = path.split('/').filter(Boolean)
  const params: Record<string, string> = {}
  let si = 0
  for (const part of p) {
    if (part.startsWith(':')) {
      const optional = part.endsWith('?')
      const name = part.slice(1, optional ? -1 : undefined)
      if (si < s.length) params[name] = decodeURIComponent(s[si++])
      else if (!optional) return null
    } else if (s[si] === part) si++
    else return null
  }
  return si === s.length ? params : null
}

export function Router({ children }: { children: React.ReactNode }) {
  const [loc, setLoc] = useState(() => window.location.pathname + window.location.search)

  useEffect(() => {
    const onPop = () => setLoc(window.location.pathname + window.location.search)
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const navigate = useCallback((to: string, opts?: { replace?: boolean }) => {
    if (to === window.location.pathname + window.location.search) return
    window.history[opts?.replace ? 'replaceState' : 'pushState'](null, '', to)
    setLoc(to)
  }, [])

  const value = useMemo(() => {
    const [path, search = ''] = loc.split('?')
    return { path, params: {}, query: new URLSearchParams(search), navigate }
  }, [loc, navigate])

  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>
}

export function useRouter(): RouteState {
  const ctx = useContext(RouterContext)
  if (!ctx) throw new Error('useRouter outside Router')
  return ctx
}

/** Renders its children only when the current path matches, passing the captured params. */
export function Route({ path, render }: { path: string; render: (params: Record<string, string>) => React.ReactNode }) {
  const { path: current } = useRouter()
  const params = match(path, current)
  return params ? <>{render(params)}</> : null
}

/** Renders only when no other listed pattern matched: the 404. */
export function NoRoute({ patterns, children }: { patterns: string[]; children: React.ReactNode }) {
  const { path } = useRouter()
  return patterns.some((p) => match(p, path)) ? null : <>{children}</>
}

export function Link({ to, children, className, ...rest }: {
  to: string
  children: React.ReactNode
  className?: string
} & React.AnchorHTMLAttributes<HTMLAnchorElement>) {
  const { navigate, path } = useRouter()
  const active = path === to || (to !== '/' && path.startsWith(to))
  return (
    <a
      href={to}
      className={className}
      aria-current={active ? 'page' : undefined}
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
        e.preventDefault()
        navigate(to)
      }}
      {...rest}
    >
      {children}
    </a>
  )
}
