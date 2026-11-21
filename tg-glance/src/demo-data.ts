import type { ChatDetail, DigestResponse } from './types'

// Built-in demo payload, used when the backend is unreachable (plain web
// preview) so the glance flow can be explored anywhere. The real backend
// serves the same shapes from the user's own Telegram account, scoped to
// an allowlist of communities.
export const DEMO_DIGEST: DigestResponse = {
  generatedAt: 'demo',
  chats: [
    {
      id: 'dow',
      title: 'Dow Protocol',
      unread: 12,
      mentions: 2,
      label: 'Dow Protocol - 12 new - 2 @you',
      hasDraft: true,
    },
    {
      id: 'qyro',
      title: 'Qyro Official',
      unread: 5,
      mentions: 0,
      label: 'Qyro Official - 5 new',
      hasDraft: false,
    },
    {
      id: 'zkv',
      title: 'zkVerify Agents',
      unread: 3,
      mentions: 0,
      label: 'zkVerify Agents - 3 new',
      hasDraft: false,
    },
    {
      id: 'base',
      title: 'Base Builders',
      unread: 2,
      mentions: 0,
      label: 'Base Builders - 2 new',
      hasDraft: false,
    },
  ],
}

export const DEMO_CHATS: Record<string, ChatDetail> = {
  dow: {
    id: 'dow',
    title: 'Dow Protocol',
    chunks: [
      'Dow Protocol - last 3h\n\n- Claim window for cycle 2 opens\n  Friday 07:00 WIB, link pinned.\n- Aurox quiz answers close\n  tonight; rewards post Monday.',
      'Dow Protocol - last 3h (2/2)\n\n- Mods remind: vault deposits\n  stay closed until the audit\n  note is published.\n- Weekly AMA moved to Sunday.',
    ],
    mentionText: '@you: does the claim window open Friday 07:00 WIB?',
    draft: {
      id: 'demo-draft-dow',
      text: 'Yes - the claim window opens Friday 07:00 WIB, link in the pinned post.',
    },
  },
  qyro: {
    id: 'qyro',
    title: 'Qyro Official',
    chunks: [
      'Qyro Official - last 3h\n\n- Neon Striker badge wave 2\n  is live for 10,000 XP holders.\n- Star Dogfight event returns\n  this weekend, 1,000 XP pool.',
    ],
  },
  zkv: {
    id: 'zkv',
    title: 'zkVerify Agents',
    chunks: [
      'zkVerify Agents - last 3h\n\n- Round 8 standings posted;\n  proof verification is lagging\n  the leaderboard by ~1 day.\n- Wildcard reviews still open.',
    ],
  },
  base: {
    id: 'base',
    title: 'Base Builders',
    chunks: [
      'Base Builders - last 3h\n\n- Builder Quest demo day\n  moved to Dec 5, submissions\n  close 23:59 UTC same day.',
    ],
  },
}
