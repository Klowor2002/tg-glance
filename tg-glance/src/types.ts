// Shared payload types between the TG Glance app and its backend.
// The backend pre-fits every string to the G2 copy budgets:
// list items <= 64 chars, digest chunks <= ~450 visible chars.

export interface ChatSummary {
  id: string
  title: string
  unread: number
  mentions: number
  /** One-line list label, already fitted to <= 64 chars by the backend. */
  label: string
  hasDraft: boolean
}

export interface DigestResponse {
  /** Backend `fetchedAt`: epoch seconds when live, "now" for demo data. */
  generatedAt: string | number
  chats: ChatSummary[]
}

export interface ChatDetail {
  id: string
  title: string
  /** Digest chunks, one per glasses page. */
  chunks: string[]
  /** The message that addresses the user, when one exists. */
  mentionText?: string
  draft?: Draft
}

export interface Draft {
  id: string
  text: string
}

export interface PairStart {
  session: string
  code: string
  expiresInSec: number
}

export type PairStatus =
  | { paired: false }
  | { paired: true; token: string; accountLabel: string }
