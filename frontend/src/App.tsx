import { useState } from "react";
import type { Role } from "./api/client";
import { AuditLogTable } from "./components/AuditLogTable";
import { ChatWindow } from "./components/ChatWindow";
import { RoleSelector } from "./components/RoleSelector";

export default function App() {
  const [role, setRole] = useState<Role>("general_employee");
  const [auditRefresh, setAuditRefresh] = useState(0);

  return (
    <div className="app-shell">
      <header>
        <div className="brand"><div className="logo">F</div><div><strong>FinBrain</strong><span>Customer intelligence, safely connected</span></div></div>
        <RoleSelector role={role} onChange={setRole} />
      </header>
      <main>
        <div className="intro"><span className="eyebrow">Customer intelligence OS</span><h1>Clarity across every conversation and transaction.</h1><p>One secure view of the signals shaping your business—without exposing sensitive customer data to AI.</p></div>
        <ChatWindow role={role} onAuditChange={() => setAuditRefresh((value) => value + 1)} />
        <AuditLogTable role={role} refreshKey={auditRefresh} />
      </main>
      <footer><span>FinBrain OS</span><span>Tokenize → reason → authorize → audit</span></footer>
    </div>
  );
}

