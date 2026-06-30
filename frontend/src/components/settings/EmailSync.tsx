'use client'

import { useState, useEffect, useCallback } from 'react'
import { toast } from 'sonner'
import type { EmailAccount, EmailProvider } from '@/types/email'
import {
  listEmailAccounts,
  connectEmail,
  disconnectEmail,
  syncEmailAccount,
} from '@/lib/api'
import { relativeTime } from '@/lib/relativeTime'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

// ---------------------------------------------------------------------------
// Privacy disclosure — shown prominently at top
// ---------------------------------------------------------------------------

function PrivacyDisclosure() {
  return (
    <div className="bg-indigo-50 border border-indigo-200 rounded-lg px-4 py-3 space-y-1.5">
      <p className="text-xs font-semibold text-indigo-800 uppercase tracking-wide">
        What we can read — and what we never do
      </p>
      <ul className="text-xs text-indigo-700 space-y-1 list-none">
        <li className="flex items-start gap-2">
          <span className="text-indigo-400 flex-none mt-0.5">✓</span>
          <span>Read-only inbox access — we cannot send, delete, or modify emails.</span>
        </li>
        <li className="flex items-start gap-2">
          <span className="text-indigo-400 flex-none mt-0.5">✓</span>
          <span>
            Only emails that match one of your tracked applications are stored.
            Unrelated email is discarded immediately and never written to disk.
          </span>
        </li>
        <li className="flex items-start gap-2">
          <span className="text-indigo-400 flex-none mt-0.5">✓</span>
          <span>
            Your OAuth access token is stored encrypted at rest and is never
            exposed in the UI or API responses.
          </span>
        </li>
        <li className="flex items-start gap-2">
          <span className="text-indigo-400 flex-none mt-0.5">✓</span>
          <span>
            One-click disconnect instantly revokes our access and removes all
            stored credentials.
          </span>
        </li>
      </ul>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Account status badge
// ---------------------------------------------------------------------------

function AccountStatusBadge({ status }: { status: EmailAccount['status'] }) {
  if (status === 'active') {
    return <span className="toggle-on">active</span>
  }
  if (status === 'paused') {
    return <span className="toggle-off">paused</span>
  }
  if (status === 'reauth_required') {
    return (
      <span className="badge badge-review">
        <span className="dot bg-amber-500" />
        re-auth required
      </span>
    )
  }
  return (
    <span className="badge badge-failed">
      <span className="dot bg-red-500" />
      revoked
    </span>
  )
}

// ---------------------------------------------------------------------------
// Connected account row
// ---------------------------------------------------------------------------

interface AccountRowProps {
  account: EmailAccount
  onSync: (id: string) => Promise<void>
  onDisconnect: (id: string) => Promise<void>
  syncingId: string | null
  disconnectingId: string | null
}

function AccountRow({
  account,
  onSync,
  onDisconnect,
  syncingId,
  disconnectingId,
}: AccountRowProps) {
  const isSyncing = syncingId === account.id
  const isDisconnecting = disconnectingId === account.id
  const lastSynced = account.last_synced_at
    ? relativeTime(account.last_synced_at)
    : 'never'
  const providerLabel =
    account.provider === 'gmail' ? 'Gmail' : 'Outlook'

  function handleDisconnectClick() {
    if (isDisconnecting) return
    const confirmed = window.confirm(
      `Disconnect ${account.email_address}? This will revoke access and remove stored credentials.`,
    )
    if (confirmed) {
      void onDisconnect(account.id)
    }
  }

  return (
    <tr className="data-row">
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="col-dot" style={{ background: account.provider === 'gmail' ? '#ea4335' : '#0078d4' }} />
          <div>
            <div className="text-sm font-medium text-foreground">{account.email_address}</div>
            <div className="text-xs text-muted-foreground">{providerLabel}</div>
          </div>
        </div>
      </td>
      <td className="px-4 py-3">
        <AccountStatusBadge status={account.status} />
      </td>
      <td className="px-4 py-3 text-xs text-muted-foreground num">{lastSynced}</td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="xs"
            className="cursor-pointer"
            onClick={() => { void onSync(account.id) }}
            disabled={isSyncing || isDisconnecting}
          >
            {isSyncing ? 'Syncing…' : 'Sync now'}
          </Button>
          <Button
            variant="ghost"
            size="xs"
            className="cursor-pointer text-red-600 hover:bg-red-50 hover:text-red-700"
            onClick={handleDisconnectClick}
            disabled={isSyncing || isDisconnecting}
          >
            {isDisconnecting ? 'Disconnecting…' : 'Disconnect'}
          </Button>
        </div>
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Connect form
// ---------------------------------------------------------------------------

interface ConnectFormProps {
  onConnect: (
    provider: EmailProvider,
    email: string,
    accessToken: string,
  ) => Promise<void>
  isConnecting: boolean
}

function ConnectForm({ onConnect, isConnecting }: ConnectFormProps) {
  const [provider, setProvider] = useState<EmailProvider>('gmail')
  const [email, setEmail] = useState('')
  const [accessToken, setAccessToken] = useState('')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (isConnecting) return
    const trimmedEmail = email.trim()
    const trimmedToken = accessToken.trim()
    if (!trimmedEmail || !trimmedToken) {
      toast.error('Email address and access token are required.')
      return
    }
    void onConnect(provider, trimmedEmail, trimmedToken)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide bg-amber-50 border border-amber-200 rounded px-2 py-0.5">
          Dev mode
        </span>
        <span className="text-xs text-muted-foreground">Connect an account using an OAuth access token directly.</span>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
            Provider
          </label>
          <Select value={provider} onValueChange={(v) => setProvider(v as EmailProvider)}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="gmail">Gmail</SelectItem>
              <SelectItem value="outlook">Outlook</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div>
          <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
            Email address
          </label>
          <Input
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
            Access token
          </label>
          <Input
            type="password"
            placeholder="ya29.…"
            value={accessToken}
            onChange={(e) => setAccessToken(e.target.value)}
            autoComplete="off"
          />
        </div>
      </div>

      <div className="flex justify-end">
        <Button
          type="submit"
          size="sm"
          className="cursor-pointer"
          disabled={isConnecting}
        >
          {isConnecting ? 'Connecting…' : 'Connect account'}
        </Button>
      </div>
    </form>
  )
}

// ---------------------------------------------------------------------------
// EmailSync section — main export
// ---------------------------------------------------------------------------

export function EmailSync() {
  const [accounts, setAccounts] = useState<EmailAccount[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isConnecting, setIsConnecting] = useState(false)
  const [syncingId, setSyncingId] = useState<string | null>(null)
  const [disconnectingId, setDisconnectingId] = useState<string | null>(null)

  const loadAccounts = useCallback((signal: AbortSignal) => {
    listEmailAccounts(signal)
      .then((data) => {
        if (signal.aborted) return
        setAccounts(data)
        setLoadError(null)
        setIsLoading(false)
      })
      .catch((err: unknown) => {
        if (signal.aborted) return
        setLoadError(err instanceof Error ? err.message : 'Failed to load email accounts.')
        setIsLoading(false)
      })
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    loadAccounts(controller.signal)
    return () => controller.abort()
  }, [loadAccounts])

  async function handleConnect(
    provider: EmailProvider,
    emailAddress: string,
    accessToken: string,
  ) {
    if (isConnecting) return
    setIsConnecting(true)
    try {
      const account = await connectEmail({
        provider,
        email_address: emailAddress,
        token: { access_token: accessToken },
      })
      setAccounts((prev) => [...prev, account])
      toast.success(`Connected ${account.email_address}`)
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to connect account.')
    } finally {
      setIsConnecting(false)
    }
  }

  async function handleSync(id: string) {
    if (syncingId !== null) return
    setSyncingId(id)
    try {
      const result = await syncEmailAccount(id)
      toast.success(
        `Sync complete — ${result.ingested} ingested, ${result.matched} matched, ${result.proposed} proposed.`,
      )
      // Refresh account list to get updated last_synced_at
      const controller = new AbortController()
      loadAccounts(controller.signal)
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Sync failed.')
    } finally {
      setSyncingId(null)
    }
  }

  async function handleDisconnect(id: string) {
    if (disconnectingId !== null) return
    setDisconnectingId(id)
    try {
      await disconnectEmail(id)
      setAccounts((prev) => prev.filter((a) => a.id !== id))
      toast.success('Account disconnected.')
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to disconnect account.')
    } finally {
      setDisconnectingId(null)
    }
  }

  return (
    <section className="bg-card border border-border rounded-xl">
      <div className="px-4 py-3 border-b border-border">
        <h2 className="text-sm font-semibold">Email sync</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Connect Gmail or Outlook to automatically detect status changes from recruiter emails.
        </p>
      </div>

      <div className="px-4 py-4 space-y-4">
        <PrivacyDisclosure />

        {/* Connected accounts */}
        <div>
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
            Connected accounts
          </h3>

          {isLoading && (
            <div className="empty py-6">Loading accounts…</div>
          )}

          {!isLoading && loadError && (
            <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-xs text-red-700 flex items-center justify-between">
              <span>{loadError}</span>
              <button
                onClick={() => {
                  const controller = new AbortController()
                  loadAccounts(controller.signal)
                }}
                className="underline text-red-600 hover:text-red-800 ml-2"
              >
                Retry
              </button>
            </div>
          )}

          {!isLoading && !loadError && accounts.length === 0 && (
            <div className="empty py-6">No accounts connected yet.</div>
          )}

          {!isLoading && !loadError && accounts.length > 0 && (
            <div className="border border-border rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-muted/80 text-muted-foreground text-xs border-b border-border">
                  <tr className="text-left">
                    <th className="px-4 py-2 font-medium">Account</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                    <th className="px-4 py-2 font-medium">Last synced</th>
                    <th className="px-4 py-2 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {accounts.map((account) => (
                    <AccountRow
                      key={account.id}
                      account={account}
                      onSync={handleSync}
                      onDisconnect={handleDisconnect}
                      syncingId={syncingId}
                      disconnectingId={disconnectingId}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Connect form */}
        <div className="border-t border-border pt-4">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
            Add account
          </h3>
          <ConnectForm onConnect={handleConnect} isConnecting={isConnecting} />
        </div>
      </div>
    </section>
  )
}
