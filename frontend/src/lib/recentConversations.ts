// Session-local stand-in for the spec's server-persisted, cross-device
// conversation list — no GET /conversations route exists yet, so this is
// scoped to this browser only. Never present as if it syncs across devices.

const STORAGE_KEY = "fb-recent-conversations";
const MAX_ENTRIES = 20;

export interface RecentConversation {
  id: string;
  title: string;
  lastActivityAt: string;
  turnCount: number;
}

function readAll(): RecentConversation[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeAll(entries: RecentConversation[]) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.slice(0, MAX_ENTRIES)));
  } catch {
    // Private-browsing / storage-disabled: recent conversations just won't persist.
  }
}

export function listRecentConversations(): RecentConversation[] {
  return readAll().sort((a, b) => new Date(b.lastActivityAt).getTime() - new Date(a.lastActivityAt).getTime());
}

// Only call this with a conversation_id the backend actually confirmed —
// never for an offline/fallback turn, so this list never implies a real
// conversation exists server-side when it doesn't.
export function recordConversationTurn(id: string, questionText: string) {
  const entries = readAll();
  const now = new Date().toISOString();
  const existing = entries.find((e) => e.id === id);
  if (existing) {
    existing.lastActivityAt = now;
    existing.turnCount += 1;
  } else {
    entries.push({ id, title: questionText.trim().slice(0, 90), lastActivityAt: now, turnCount: 1 });
  }
  writeAll(entries);
}
