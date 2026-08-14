import { useAppState } from "../lib/appState";
import { PERSONAS, PERSONA_LIST } from "../lib/personas";

export function PersonaSelector({ compact = false }: { compact?: boolean }) {
  const { askRole, setAskRole } = useAppState();
  const active = PERSONAS[askRole];
  return (
    <div className={compact ? "fb-persona-selector is-compact" : "fb-persona-selector"}>
      <div>
        <span className="fb-eyebrow">Demo persona</span>
        <div className="fb-fine">Authentication is not implemented.</div>
      </div>
      <select
        className="fb-field-mock"
        value={askRole}
        onChange={(event) => setAskRole(event.target.value as typeof askRole)}
        aria-label="Demo persona"
      >
        {PERSONA_LIST.map((persona) => (
          <option value={persona.role} key={persona.role}>{persona.label}</option>
        ))}
      </select>
      {!compact && <div className="fb-fine">{active.description}</div>}
    </div>
  );
}
