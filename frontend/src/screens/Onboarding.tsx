import { useState } from "react";
import { useAppState } from "../lib/appState";
import { Wordmark } from "../components/Logo";

const ITEMS = [
  { title: "Connect Gmail", detail: "Let the Invoicing Agent watch for incoming receipts." },
  { title: "Connect Google Drive & Sheets", detail: "Keep folders organized and logs updated automatically." },
  { title: "Invite a teammate", detail: "Add your finance team so approvals don't bottleneck on you." },
  { title: "Ask your first question", detail: 'Try "What e-invoices need my approval?" once you\'re in.' },
];

export default function Onboarding() {
  const { show, signupName, signupCompany, enterSampleWorkspace } = useAppState();
  const [done, setDone] = useState<boolean[]>(() => ITEMS.map(() => false));

  const firstName = signupName.split(" ")[0];
  const greeting = firstName ? `Welcome, ${firstName}!` : "Welcome!";
  const sub = signupCompany
    ? `Your workspace at ${signupCompany} is ready. A few quick things before you dive in — or skip straight to a live sample workspace.`
    : "Your workspace is ready. A few quick things before you dive in — or skip straight to a live sample workspace.";

  return (
    <div className="fb-root">
      <nav className="fb-nav">
        <Wordmark onClick={() => show("landing")} />
      </nav>
      <div className="fb-page-body" style={{ maxWidth: "560px", paddingTop: "3rem", textAlign: "center" }}>
        <div className="fb-eyebrow">Welcome</div>
        <h1 style={{ fontFamily: "Georgia,'Times New Roman',serif", fontSize: "1.6rem", fontWeight: 500, margin: ".6rem 0 1rem" }}>{greeting}</h1>
        <p style={{ color: "var(--ink-soft)", fontSize: ".85rem", fontFamily: "Arial,Helvetica,sans-serif" }}>{sub}</p>

        <div className="fb-onboarding-checklist">
          {ITEMS.map((item, i) => (
            <button
              key={item.title}
              className={"fb-onboarding-item" + (done[i] ? " is-done" : "")}
              type="button"
              onClick={() => setDone((d) => d.map((v, idx) => (idx === i ? !v : v)))}
            >
              <span className="fb-onboarding-check" aria-hidden="true"></span>
              <div><strong>{item.title}</strong><span className="fb-onboarding-detail">{item.detail}</span></div>
            </button>
          ))}
        </div>

        <button className="fb-btn fb-btn-solid" style={{ width: "100%" }} type="button" onClick={enterSampleWorkspace}>Explore with sample data</button>
        <p className="fb-fine">These steps are optional — you can connect your own sources anytime.</p>
      </div>
    </div>
  );
}
