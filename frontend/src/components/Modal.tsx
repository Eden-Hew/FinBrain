import { useEffect, type ReactNode } from "react";

// Shared dialog shell so every modal in the app closes on backdrop click and
// Escape — the hand-rolled overlays this replaces only closed via an explicit
// Cancel button, which is a familiar-but-missing affordance most users expect.
export function Modal({ onClose, children, maxWidth = "600px" }: { onClose: () => void; children: ReactNode; maxWidth?: string }) {
  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }}
      onClick={onClose}
    >
      <div
        style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: "14px", padding: "1.5rem", maxWidth, width: "90%", maxHeight: "90vh", overflowY: "auto", boxShadow: "0 20px 50px -10px rgba(0,0,0,0.4)" }}
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        {children}
      </div>
    </div>
  );
}
