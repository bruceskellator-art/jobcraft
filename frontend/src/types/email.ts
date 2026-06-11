export type EmailProvider = 'gmail' | 'outlook'

export type EmailAccountStatus = 'active' | 'paused' | 'reauth_required' | 'revoked'

export interface EmailAccount {
  id: string
  provider: EmailProvider
  email_address: string
  scopes: string[]
  status: EmailAccountStatus
  connected_at: string
  last_synced_at: string | null
}

export interface SyncResult {
  ingested: number
  matched: number
  applied: number
  proposed: number
}

export type StatusEventState = 'proposed' | 'applied' | 'dismissed'

export interface StatusEvent {
  id: string
  application_id: string
  from_status: string | null
  to_status: string
  classification: string
  confidence: number
  state: StatusEventState
  created_at: string
  resolved_at: string | null
}

export interface ConnectEmailBody {
  provider: EmailProvider
  email_address: string
  token: {
    access_token: string
    scope?: string
    [key: string]: string | undefined
  }
}
