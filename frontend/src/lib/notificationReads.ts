// Client-side read tracking for the notification bell -- same pattern as
// recentConversations.ts (session-local, disclosed, never presented as if
// it syncs across devices). There's no backend concept of "read" for these
// items since they're aggregated from several existing endpoints, so this
// is scoped to "seen on this device" rather than a real server-side flag.

const STORAGE_KEY = "fb-notif-read-ids";
const MAX_ENTRIES = 300;

function readAll(): string[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeAll(ids: string[]) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(ids.slice(-MAX_ENTRIES)));
  } catch {
    // Private-browsing / storage-disabled: read state just won't persist.
  }
}

export function getReadIds(): Set<string> {
  return new Set(readAll());
}

export function markRead(id: string) {
  const ids = readAll();
  if (!ids.includes(id)) writeAll([...ids, id]);
}

export function markManyRead(ids: string[]) {
  const existing = readAll();
  const next = [...existing];
  for (const id of ids) if (!next.includes(id)) next.push(id);
  writeAll(next);
}
