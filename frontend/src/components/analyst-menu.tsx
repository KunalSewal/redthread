import { useState } from 'react'
import { LogOut, UserRound } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { SNAPSHOT } from '@/lib/api'
import { useAnalyst } from '@/lib/analyst'

export function SignInDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { signIn } = useAnalyst()
  const [key, setKey] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const who = await signIn(key)
      toast.success(`Signed in as ${who.name}`)
      setKey('')
      onOpenChange(false)
    } catch (err) {
      setError(SNAPSHOT ? 'Signing in needs the live backend. The recorded snapshot has no analysts.' : (err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Sign in as an analyst</DialogTitle>
            <DialogDescription>
              Paste the analyst key you were given. Every decision you make is recorded against it.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="analyst-key">Analyst key</Label>
            <Input
              id="analyst-key"
              type="password"
              autoComplete="off"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              aria-invalid={error ? true : undefined}
              autoFocus
            />
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>
          <DialogFooter>
            <Button type="submit" disabled={!key.trim() || busy}>
              {busy ? 'Checking the key' : 'Sign in'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function AnalystMenu() {
  const { analyst, signOut } = useAnalyst()
  const [open, setOpen] = useState(false)

  if (!analyst) {
    return (
      <>
        <Button variant="outline" size="sm" onClick={() => setOpen(true)} aria-label="Sign in">
          <UserRound />
          <span className="hidden sm:inline">Sign in</span>
        </Button>
        <SignInDialog open={open} onOpenChange={setOpen} />
      </>
    )
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger render={<Button variant="ghost" size="sm" />}>
          <span className="grid size-6 place-items-center rounded-full bg-primary text-[0.7rem] font-semibold text-primary-foreground">
            {analyst.name.slice(0, 1).toUpperCase()}
          </span>
          {analyst.name}
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuGroup>
            <DropdownMenuLabel>Signed in as {analyst.name}</DropdownMenuLabel>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <DropdownMenuItem onClick={() => setOpen(true)}>
              <UserRound />
              Switch analyst
            </DropdownMenuItem>
            <DropdownMenuItem onClick={signOut}>
              <LogOut />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
      <SignInDialog open={open} onOpenChange={setOpen} />
    </>
  )
}
