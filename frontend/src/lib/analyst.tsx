import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { api, type Analyst } from './api'

/* The analyst at the keyboard. There is one role; the server still knows each person by their key and
 * records every decision against them, and a contested challenge needs a second, different analyst.
 * The key lives for the browser session only. */

interface Signed extends Analyst { key: string }
interface AnalystContext {
  analyst: Signed | null
  signIn: (key: string) => Promise<Signed>
  signOut: () => void
}

const STORAGE = 'redthread.analyst'
const Context = createContext<AnalystContext | null>(null)

function stored(): Signed | null {
  try {
    const raw = sessionStorage.getItem(STORAGE)
    return raw ? (JSON.parse(raw) as Signed) : null
  } catch {
    return null
  }
}

export function AnalystProvider({ children }: { children: ReactNode }) {
  const [analyst, setAnalyst] = useState<Signed | null>(stored)

  const signIn = useCallback(async (key: string) => {
    const who = await api.whoami(key.trim())
    const signed = { ...who, key: key.trim() }
    setAnalyst(signed)
    try {
      sessionStorage.setItem(STORAGE, JSON.stringify(signed))
    } catch {
      /* private window: signed in for this page only */
    }
    return signed
  }, [])

  const signOut = useCallback(() => {
    setAnalyst(null)
    try {
      sessionStorage.removeItem(STORAGE)
    } catch {
      /* nothing stored */
    }
  }, [])

  const value = useMemo(() => ({ analyst, signIn, signOut }), [analyst, signIn, signOut])
  return <Context.Provider value={value}>{children}</Context.Provider>
}

export function useAnalyst() {
  const ctx = useContext(Context)
  if (!ctx) throw new Error('useAnalyst needs an AnalystProvider')
  return ctx
}
