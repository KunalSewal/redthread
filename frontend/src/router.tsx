import { createBrowserRouter, Link } from 'react-router'
import { AppShell } from '@/components/app-shell'
import { Button } from '@/components/ui/button'
import { CasesPage } from '@/pages/cases'
import { DashboardPage } from '@/pages/dashboard'
import { LandingPage } from '@/pages/landing'

function NotFound() {
  return (
    <div className="grid min-h-[60svh] place-items-center text-center">
      <div className="space-y-3">
        <h1 className="text-xl font-semibold">There is no page here</h1>
        <p className="text-muted-foreground">The link may be out of date.</p>
        <Button render={<Link to="/app" />}>Go to the dashboard</Button>
      </div>
    </div>
  )
}

export const router = createBrowserRouter([
  { path: '/', element: <LandingPage /> },
  {
    path: '/app',
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'cases', element: <CasesPage /> },
      { path: 'cases/:caseId', element: <CasesPage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
  { path: '*', element: <NotFound /> },
])
