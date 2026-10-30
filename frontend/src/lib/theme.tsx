import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

/* Light, dark, or follow the system. The choice is a per-viewer convenience kept in localStorage; the
 * class on <html> is set before first paint by the inline script in index.html. */

export type Theme = 'light' | 'dark' | 'system'
const STORAGE = 'redthread.theme'
const Context = createContext<{ theme: Theme; resolved: 'light' | 'dark'; setTheme: (t: Theme) => void } | null>(null)

function read(): Theme {
  try {
    const t = localStorage.getItem(STORAGE)
    return t === 'light' || t === 'dark' ? t : 'system'
  } catch {
    return 'system'
  }
}

const media = () => window.matchMedia('(prefers-color-scheme: dark)')

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(read)
  const [systemDark, setSystemDark] = useState(() => media().matches)

  useEffect(() => {
    const m = media()
    const on = (e: MediaQueryListEvent) => setSystemDark(e.matches)
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [])

  const resolved = theme === 'system' ? (systemDark ? 'dark' : 'light') : theme

  useEffect(() => {
    document.documentElement.classList.toggle('dark', resolved === 'dark')
    document.documentElement.style.colorScheme = resolved
  }, [resolved])

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t)
    try {
      if (t === 'system') localStorage.removeItem(STORAGE)
      else localStorage.setItem(STORAGE, t)
    } catch {
      /* storage blocked: the choice lasts for this page */
    }
  }, [])

  const value = useMemo(() => ({ theme, resolved, setTheme }), [theme, resolved, setTheme])
  return <Context.Provider value={value}>{children}</Context.Provider>
}

export function useTheme() {
  const ctx = useContext(Context)
  if (!ctx) throw new Error('useTheme needs a ThemeProvider')
  return ctx
}
