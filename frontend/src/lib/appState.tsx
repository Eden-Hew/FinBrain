import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import {
  FB_ROLE_IDENTITY,
  initialAuditRows,
  initialEinvoices,
  initialPendingActions,
  initialRecommendations,
  initialSops,
  type AskRole,
  type AuditRow,
  type EinvoiceRecord,
  type PendingAction,
  type Recommendation,
  type Sop,
} from "../data/sampleData";

export type Screen =
  | "landing" | "login" | "signup" | "onboarding" | "security" | "legal"
  | "agents" | "einvoice" | "einvoice-detail" | "finance" | "audit" | "approvals" | "ingestion";

interface AppStateValue {
  screen: Screen;
  show: (screen: Screen) => void;

  returnTo: "landing" | "login" | "signup";
  goToSecurity: (returnTo?: "landing" | "login" | "signup") => void;
  goToLegal: (section: "privacy" | "terms", returnTo?: "landing" | "login" | "signup") => void;
  legalSection: "privacy" | "terms";
  contextBack: () => void;

  signupName: string;
  signupCompany: string;
  setSignupInfo: (name: string, company: string) => void;

  sampleBanner: boolean;
  enterSampleWorkspace: () => void;
  dismissSampleBanner: () => void;

  askRole: AskRole;
  setAskRole: (role: AskRole) => void;

  einvoices: Record<string, EinvoiceRecord>;
  currentEinvoiceId: string | null;
  showEinvoiceDetail: (id: string) => void;
  approveEinvoiceById: (id: string) => void;
  rejectEinvoiceById: (id: string) => void;

  einvoiceFilterMine: boolean;
  setEinvoiceFilterMine: (mine: boolean) => void;

  sops: Sop[];
  approveSop: (id: string) => void;
  rejectSop: (id: string) => void;
  draftSop: (recId: string) => void;

  recommendations: Recommendation[];

  auditRows: AuditRow[];
  auditBaseCount: number;
  pushAuditRow: (actor: string, type: string, resource: string, grant: string, status: "Allowed" | "Denied") => void;

  pendingActions: PendingAction[];
  approveAction: (id: string) => void;
  rejectAction: (id: string) => void;

  approvalsCount: number;
}

const AppStateContext = createContext<AppStateValue | null>(null);

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [screen, setScreen] = useState<Screen>("landing");
  const [returnTo, setReturnTo] = useState<"landing" | "login" | "signup">("landing");
  const [legalSection, setLegalSection] = useState<"privacy" | "terms">("privacy");
  const [signupName, setSignupName] = useState("");
  const [signupCompany, setSignupCompany] = useState("");
  const [sampleBanner, setSampleBanner] = useState(false);
  const [askRole, setAskRoleState] = useState<AskRole>("finance_director");
  const [einvoices, setEinvoices] = useState<Record<string, EinvoiceRecord>>(() => initialEinvoices());
  const [currentEinvoiceId, setCurrentEinvoiceId] = useState<string | null>(null);
  const [einvoiceFilterMine, setEinvoiceFilterMine] = useState(false);
  const [sops, setSops] = useState<Sop[]>(() => initialSops());
  const [recommendations, setRecommendations] = useState<Recommendation[]>(() => initialRecommendations());
  const [auditRows, setAuditRows] = useState<AuditRow[]>(() => initialAuditRows());
  const [pendingActions, setPendingActions] = useState<PendingAction[]>(() => initialPendingActions());

  const show = useCallback((s: Screen) => {
    setScreen(s);
    window.scrollTo(0, 0);
  }, []);

  const goToSecurity = useCallback((rt?: "landing" | "login" | "signup") => {
    if (rt !== undefined) setReturnTo(rt);
    show("security");
  }, [show]);

  const goToLegal = useCallback((section: "privacy" | "terms", rt?: "landing" | "login" | "signup") => {
    if (rt !== undefined) setReturnTo(rt);
    setLegalSection(section);
    show("legal");
    setTimeout(() => document.getElementById("legal-" + section)?.scrollIntoView(), 0);
  }, [show]);

  const contextBack = useCallback(() => {
    show(returnTo === "login" || returnTo === "signup" ? returnTo : "landing");
  }, [returnTo, show]);

  const setSignupInfo = useCallback((name: string, company: string) => {
    setSignupName(name);
    setSignupCompany(company);
  }, []);

  const enterSampleWorkspace = useCallback(() => {
    setSampleBanner(true);
    show("agents");
  }, [show]);

  const dismissSampleBanner = useCallback(() => setSampleBanner(false), []);

  const setAskRole = useCallback((role: AskRole) => setAskRoleState(role), []);

  const pushAuditRow = useCallback((actor: string, type: string, resource: string, grant: string, status: "Allowed" | "Denied") => {
    setAuditRows((rows) => [
      {
        time: new Date().toTimeString().slice(0, 8),
        actor, type, resource, grant, status,
        hash: Math.random().toString(16).slice(2, 8) + "…",
      },
      ...rows,
    ]);
  }, []);

  const showEinvoiceDetail = useCallback((id: string) => {
    setCurrentEinvoiceId(id);
    show("einvoice-detail");
  }, [show]);

  const approveEinvoiceById = useCallback((id: string) => {
    setEinvoices((prev) => {
      const inv = prev[id];
      if (!inv || inv.status === "review") return prev;
      const uin = "MY29A" + Math.random().toString(36).slice(2, 8).toUpperCase();
      const updated: EinvoiceRecord = {
        ...inv,
        status: "validated",
        uin,
        compliance: [
          ...inv.compliance,
          ["Submitted", "Digitally signed and sent to MyInvois sandbox."],
          ["Validated", "LHDN returned a UIN and QR code."],
        ],
      };
      pushAuditRow("chloe@finbrain.my", "e-Invoice Approved", inv.supplier + " · " + inv.amount, "finance_director", "Allowed");
      return { ...prev, [id]: updated };
    });
  }, [pushAuditRow]);

  const rejectEinvoiceById = useCallback((id: string) => {
    setEinvoices((prev) => {
      const inv = prev[id];
      if (!inv) return prev;
      const updated: EinvoiceRecord = {
        ...inv,
        status: "review",
        compliance: [...inv.compliance, ["Sent back", "Returned by Finance Director for correction before resubmission."]],
      };
      pushAuditRow("chloe@finbrain.my", "e-Invoice Sent Back", inv.supplier + " · " + inv.amount, "finance_director", "Denied");
      return { ...prev, [id]: updated };
    });
  }, [pushAuditRow]);

  const approveSop = useCallback((id: string) => {
    setSops((prev) => {
      const sop = prev.find((s) => s.id === id);
      if (!sop || sop.status === "approved") return prev;
      const nextVersion = sop.version + 1;
      pushAuditRow("chloe@finbrain.my", "SOP Approval", sop.title + " v" + nextVersion, "finance_director", "Allowed");
      return prev.map((s) => (s.id === id ? { ...s, status: "approved", version: nextVersion } : s));
    });
  }, [pushAuditRow]);

  const rejectSop = useCallback((id: string) => {
    setSops((prev) => {
      const sop = prev.find((s) => s.id === id);
      if (!sop) return prev;
      pushAuditRow("chloe@finbrain.my", "SOP Discarded", sop.title, "finance_director", "Denied");
      if (sop.sourceRecId) {
        setRecommendations((recs) => recs.map((r) => (r.id === sop.sourceRecId ? { ...r, status: "proposed" } : r)));
      }
      return prev.filter((s) => s.id !== id);
    });
  }, [pushAuditRow]);

  const draftSop = useCallback((recId: string) => {
    setRecommendations((prev) => {
      const rec = prev.find((r) => r.id === recId);
      if (!rec || rec.status === "sop_drafted") return prev;
      setSops((sops) => [
        ...sops,
        {
          id: "sop-" + recId, title: rec.title, version: 1, status: "draft", owner: "Chloe Tan", sourceRecId: recId,
          steps: [
            { n: "1", t: "Review evidence", d: rec.evidence },
            { n: "2", t: "Confirm the policy change", d: "Align with finance ops before rollout." },
            { n: "3", t: "Update agent configuration", d: "Apply the new rule in the relevant AI Agent's settings." },
          ],
        },
      ]);
      return prev.map((r) => (r.id === recId ? { ...r, status: "sop_drafted" } : r));
    });
  }, []);

  const approveAction = useCallback((id: string) => {
    setPendingActions((prev) => {
      const act = prev.find((a) => a.id === id);
      if (!act || !act.active) return prev;
      pushAuditRow(act.agent.toLowerCase().replace(/[^a-z]+/g, "-"), act.kind + " Sent", act.title, "system", "Allowed");
      return prev.map((a) => (a.id === id ? { ...a, active: false } : a));
    });
  }, [pushAuditRow]);

  const rejectAction = useCallback((id: string) => {
    setPendingActions((prev) => {
      const act = prev.find((a) => a.id === id);
      if (!act || !act.active) return prev;
      pushAuditRow("chloe@finbrain.my", act.kind + " Discarded", act.title, "finance_director", "Denied");
      return prev.map((a) => (a.id === id ? { ...a, active: false } : a));
    });
  }, [pushAuditRow]);

  const approvalsCount = useMemo(() => {
    let count = 0;
    Object.values(einvoices).forEach((inv) => { if (inv.status === "pending") count++; });
    sops.forEach((s) => { if (s.status === "draft") count++; });
    pendingActions.forEach((a) => { if (a.active) count++; });
    return count;
  }, [einvoices, sops, pendingActions]);

  const value: AppStateValue = {
    screen, show,
    returnTo, goToSecurity, goToLegal, legalSection, contextBack,
    signupName, signupCompany, setSignupInfo,
    sampleBanner, enterSampleWorkspace, dismissSampleBanner,
    askRole, setAskRole,
    einvoices, currentEinvoiceId, showEinvoiceDetail, approveEinvoiceById, rejectEinvoiceById,
    einvoiceFilterMine, setEinvoiceFilterMine,
    sops, approveSop, rejectSop, draftSop,
    recommendations,
    auditRows, auditBaseCount: 122, pushAuditRow,
    pendingActions, approveAction, rejectAction,
    approvalsCount,
  };

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState() {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error("useAppState must be used within AppStateProvider");
  return ctx;
}

export function submitterName(email: string | null): string {
  if (!email) return "—";
  const match = (Object.keys(FB_ROLE_IDENTITY) as AskRole[]).find((k) => FB_ROLE_IDENTITY[k].email === email);
  return match ? FB_ROLE_IDENTITY[match].name : email;
}
