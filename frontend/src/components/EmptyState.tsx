import type { ReactNode } from "react";

/** Shared empty-state pattern: icon + message + optional action, so "there's
 * nothing here yet" always tells the user what to do next instead of leaving
 * a blank table. Every screen previously wrote its own bespoke text-only
 * version of this with no consistent styling and no call-to-action. */
export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <div className="fb-empty-state">
      {icon && <div className="fb-empty-state-icon" aria-hidden="true">{icon}</div>}
      <div className="fb-empty-state-title">{title}</div>
      {description && <p className="fb-empty-state-desc">{description}</p>}
      {action && (
        <button className="fb-btn fb-btn-solid fb-empty-state-action" type="button" onClick={action.onClick}>
          {action.label}
        </button>
      )}
    </div>
  );
}
