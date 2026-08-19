import { useEffect, useMemo, useRef, useState } from "react";
import { useAppState, type Screen } from "../lib/appState";
import { useAuth } from "../auth/AuthProvider";
import { useTheme } from "../lib/theme";
import { useUiChrome } from "../lib/uiChrome";

interface Command {
  id: string;
  label: string;
  hint: string;
  run: () => void;
}

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
  const { toggle: toggleTheme } = useTheme();
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const destinations: { screen: Screen; label: string }[] = [
    { screen: "agents", label: "Customer Intelligence" },
    { screen: "einvoice", label: "e-Invoicing" },
    { screen: "finance", label: "Finance Dashboard" },
    { screen: "audit", label: "Audit Trail" },
    { screen: "approvals", label: "Approvals" },
    { screen: "ingestion", label: "Ingestion" },
  ];

  const commands: Command[] = useMemo(() => [
    ...destinations.map((d) => ({
      id: "go-" + d.screen,
      label: d.label,
      hint: "Go to page",
      run: () => show(d.screen),
    })),
    { id: "ask", label: "Ask FinBrain", hint: "Open the AI assistant", run: () => openAsk() },
    { id: "theme", label: "Toggle light / dark theme", hint: "Appearance", run: () => toggleTheme() },
    { id: "logout", label: "Log out", hint: "Account", run: () => { void signOut().then(() => show("landing")); } },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [show, openAsk, toggleTheme, signOut]);

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
              <span>{command.label}</span>
              <span className="fb-palette-hint">{command.hint}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
