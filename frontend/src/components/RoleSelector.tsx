import type { Role } from "../api/client";

const ROLES: { value: Role; label: string; description: string }[] = [
  { value: "general_employee", label: "General employee", description: "Basic contact access" },
  { value: "finance_ops", label: "Finance / operations", description: "Account and payment access" },
  { value: "owner_director", label: "Owner / director", description: "Broad operational access" },
  { value: "compliance", label: "Compliance", description: "Sensitive and audit access" },
];

interface Props {
  role: Role;
  onChange: (role: Role) => void;
}

export function RoleSelector({ role, onChange }: Props) {
  const selected = ROLES.find((item) => item.value === role)!;
  return (
    <div className="role-control">
      <label htmlFor="role">Viewing as</label>
      <select id="role" value={role} onChange={(event) => onChange(event.target.value as Role)}>
        {ROLES.map((item) => (
          <option key={item.value} value={item.value}>{item.label}</option>
        ))}
      </select>
      <span>{selected.description}</span>
    </div>
  );
}

