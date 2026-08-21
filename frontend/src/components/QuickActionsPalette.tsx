import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useAppState, type Screen } from "../lib/appState";
import { useAuth } from "../auth/AuthProvider";
import { useI18n } from "../lib/i18n";
import { useUiChrome } from "../lib/uiChrome";

interface Command {
  id: string;
  label: string;
  hint: string;
  icon?: ReactNode;
  run: () => void;
}

const DESTINATION_ICONS: Record<string, ReactNode> = {
  home: <><path d="M3 11l9-7 9 7" /><path d="M5 10v9a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1v-9" /></>,
  agents: <path d="M4 4h13a3 3 0 0 1 3 3v7a3 3 0 0 1-3 3H9l-5 3v-3a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3z" />,
  customers: <><circle cx="9" cy="7" r="3.2" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><circle cx="17.5" cy="8.5" r="2.4" /><path d="M15.3 12.3A5.2 5.2 0 0 1 21.5 17" /></>,
  einvoice: <path d="M6 2h9l3 3v17H6z M9 8h6M9 12h6M9 16h4" />,
  finance: <path d="M4 19V9M10 19V5M16 19v-7M22 19H2" />,
  approvals: <path d="M9 12l2 2 4-4M12 3l8 4v5c0 4.5-3.2 8.5-8 10-4.8-1.5-8-5.5-8-10V7z" />,
  ingestion: <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 9l5-5 5 5M12 4v13" />,
  audit: <path d="M12 3 20 6.5v5.3c0 4.7-3.2 8.9-8 10.2-4.8-1.3-8-5.5-8-10.2V6.5z" />,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></>,
};

// Split so the search state lives only while the palette is open: mounting a fresh
// PaletteBody on every open gives clean query/highlight defaults for free, instead of
// an always-mounted component resetting its own state via an effect on every open.
export function QuickActionsPalette() {
  const { paletteOpen } = useUiChrome();
  if (!paletteOpen) return null;
  return <PaletteBody />;
}

function PaletteBody() {
  const { closePalette, openAsk } = useUiChrome();
  const { show } = useAppState();
  const { signOut } = useAuth();
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Same screens, same order, and the same i18n keys as the sidebar (Nav.tsx's
  // NAV_GROUPS), so this list can't drift out of sync with real navigation again.
  const destinations: { screen: Screen; key: string }[] = [
    { screen: "home", key: "nav.home" },
    { screen: "agents", key: "nav.aiAgents" },
    { screen: "customers", key: "nav.customers" },
    { screen: "einvoice", key: "nav.einvoicing" },
    { screen: "finance", key: "nav.financeDashboard" },
    { screen: "approvals", key: "nav.approvals" },
    { screen: "ingestion", key: "nav.ingestion" },
    { screen: "audit", key: "nav.audit" },
    { screen: "settings", key: "nav.settings" },
  ];

  const commands: Command[] = useMemo(() => [
    ...destinations.map((d) => ({
      id: "go-" + d.screen,
      label: t(d.key),
      hint: "Go to page",
      icon: DESTINATION_ICONS[d.screen],
      run: () => show(d.screen),
    })),
    { id: "ask", label: "Ask FinBrain", hint: "Open the AI assistant", run: () => openAsk() },
    { id: "logout", label: "Log out", hint: "Account", run: () => { void signOut().then(() => show("landing")); } },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [show, openAsk, signOut, t]);

  const filtered = commands.filter((c) => c.label.toLowerCase().includes(query.toLowerCase()));

  useEffect(() => {
    requestAnimationFrame(() => inputRef.current?.focus());
  }, []);

  // Reset the highlighted row when the query changes, computed during render (React's
  // documented pattern for "adjusting state when a prop/state changes") rather than in
  // an effect, so it doesn't cost an extra commit-then-reset render pass.
  const [prevQuery, setPrevQuery] = useState(query);
  if (query !== prevQuery) {
    setPrevQuery(query);
    setHighlight(0);
  }

  const runCommand = (command: Command) => {
    command.run();
    closePalette();
  };

  return (
    <div className="fb-palette-backdrop" onClick={closePalette}>
      <div
        className="fb-palette"
        role="dialog"
        aria-modal="true"
        aria-label="Quick actions"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") { event.preventDefault(); setHighlight((h) => Math.min(h + 1, filtered.length - 1)); }
          if (event.key === "ArrowUp") { event.preventDefault(); setHighlight((h) => Math.max(h - 1, 0)); }
          if (event.key === "Enter" && filtered[highlight]) { event.preventDefault(); runCommand(filtered[highlight]); }
          if ((event.metaKey || event.ctrlKey) && /^[1-9]$/.test(event.key)) {
            const target = filtered[Number(event.key) - 1];
            if (target) { event.preventDefault(); runCommand(target); }
          }
        }}
      >
        <div className="fb-palette-input-row">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></svg>
          <input
            ref={inputRef}
            className="fb-palette-input"
            type="text"
            placeholder="Search pages and actions…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <span className="fb-palette-esc">Esc</span>
        </div>
        <div className="fb-palette-list" role="listbox">
          {filtered.length === 0 && <div className="fb-palette-empty">No matches</div>}
          {filtered.map((command, i) => (
            <button
              key={command.id}
              type="button"
              className={"fb-palette-item" + (i === highlight ? " is-highlighted" : "")}
              onMouseEnter={() => setHighlight(i)}
              onClick={() => runCommand(command)}
              role="option"
              aria-selected={i === highlight}
            >
              <span className="fb-palette-item-left">
                {command.icon && (
                  <svg className="fb-palette-item-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{command.icon}</svg>
                )}
                <span>{command.label}</span>
              </span>
              <span className="fb-palette-item-right">
                {i < 9 && <span className="fb-palette-esc fb-palette-kbd">⌘{i + 1}</span>}
                <span className="fb-palette-hint">{command.hint}</span>
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
