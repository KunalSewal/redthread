import { useEffect, useRef } from 'react'
import { Link, NoRoute, Route, Router, useRouter } from './router'
import { CaseFile } from './pages/CaseFile'
import { Docket } from './pages/Docket'
import { Missed } from './pages/Missed'
import { Rings } from './pages/Rings'
import { Trust } from './pages/Trust'
import './app.css'

const ROUTES = ['/', '/case/:id', '/missed', '/rings/:id?', '/trust']

/** The thread, drawn. It is the product's mark and the only decorative use of the accent. */
function Mark() {
  return (
    <svg className="mark" width="30" height="20" viewBox="0 0 30 20" aria-hidden="true">
      <path d="M1 15 C7 -2, 13 21, 29 4" stroke="var(--thread)" strokeWidth="2.2" fill="none" strokeLinecap="round" />
    </svg>
  )
}

/** Moving to a new page should move the reader, not just the scroll position. */
function FocusOnRouteChange() {
  const { path } = useRouter()
  const first = useRef(true)
  useEffect(() => {
    if (first.current) { first.current = false; return }
    window.scrollTo(0, 0)
    const heading = document.querySelector<HTMLElement>('main h2')
    heading?.setAttribute('tabindex', '-1')
    heading?.focus({ preventScroll: true })
  }, [path])
  return null
}

function Masthead() {
  return (
    <header className="masthead">
      <Link to="/" className="brand">
        <Mark />
        <span className="brand-name">RedThread</span>
      </Link>
      <nav aria-label="Sections">
        <Link to="/">Docket</Link>
        <Link to="/missed">What the queue missed</Link>
        <Link to="/rings">Rings</Link>
        <Link to="/trust">Should you believe it</Link>
      </nav>
      <p className="masthead-note">Agentic fraud investigation on TigerGraph</p>
    </header>
  )
}

export default function App() {
  return (
    <Router>
      <FocusOnRouteChange />
      <div className="shell">
        <Masthead />
        <Route path="/" render={() => <Docket />} />
        <Route path="/case/:id" render={(p) => <CaseFile key={p.id} id={p.id} />} />
        <Route path="/missed" render={() => <Missed />} />
        <Route path="/rings/:id?" render={(p) => <Rings ringId={p.id} />} />
        <Route path="/trust" render={() => <Trust />} />
        <NoRoute patterns={ROUTES}>
          <main className="page">
            <h2>No such page</h2>
            <p className="prose">That address does not match anything here. <Link to="/">Back to the docket</Link>.</p>
          </main>
        </NoRoute>
      </div>
    </Router>
  )
}
