import { useAppState } from "../lib/appState";
import { PERSONAS } from "../lib/personas";

export function PersonaSelector({ compact = false }: { compact?: boolean }) {
  const { askRole } = useAppState();
  const active = PERSONAS[askRole];
  return (
    <div className={compact ? "fb-persona-selector is-compact" : "fb-persona-selector"}>
      <div>
        <span className="fb-eyebrow">Authenticated role</span>
        <div className="fb-fine">Assigned by your administrator.</div>
      </div>
      <strong className="fb-field-mock" aria-label="Authenticated role">{active.label}</strong>
      {!compact && <div className="fb-fine">{active.description}</div>}
    </div>
  );
}
