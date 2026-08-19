import { useEffect } from "react";
import { AuthProvider, useAuth } from "./auth/AuthProvider";
import { AppStateProvider, useAppState } from "./lib/appState";
import { I18nProvider } from "./lib/i18n";
import { ThemeProvider, ThemeToggleButton } from "./lib/theme";
import { UiChromeProvider } from "./lib/uiChrome";
import { AskDrawer } from "./components/AskDrawer";
import { QuickActionsPalette } from "./components/QuickActionsPalette";

import Landing from "./screens/Landing";
import Login from "./screens/Login";
import Signup from "./screens/Signup";
import Onboarding from "./screens/Onboarding";
import Security from "./screens/Security";
import Legal from "./screens/Legal";
import Agents from "./screens/Agents";
import Einvoice from "./screens/Einvoice";
import EinvoiceDetail from "./screens/EinvoiceDetail";
import Finance from "./screens/Finance";
import Audit from "./screens/Audit";
import Approvals from "./screens/Approvals";
import Ingestion from "./screens/Ingestion";

function GlobalThemeToggle() {
  // The landing page has its own inline toggle in the marketing nav, so the
  // floating one is suppressed there to avoid stacking two theme controls
  // in the same bottom-right corner as the support chat launcher.
  const { screen } = useAppState();
  if (screen === "landing") return null;
  return <ThemeToggleButton />;
}

function Screens() {
  const { screen, show, setAskRole } = useAppState();
  const { identity, loading } = useAuth();
  const isPublic = ["landing", "login", "signup", "security", "legal"].includes(screen);

  useEffect(() => {
    if (identity) setAskRole(identity.role);
  }, [identity, setAskRole]);

  useEffect(() => {
    if (!loading && !identity && !isPublic) show("login");
    if (!loading && identity && (screen === "login" || screen === "signup")) show("agents");
  }, [identity, isPublic, loading, screen, show]);

  if (loading) {
    return <div className="fb-root"><div className="fb-callout">Checking secure session…</div></div>;
  }

  switch (screen) {
    case "landing": return <Landing />;
    case "login": return <Login />;
    case "signup": return <Signup />;
    case "onboarding": return <Onboarding />;
    case "security": return <Security />;
    case "legal": return <Legal />;
    case "agents": return <Agents />;
    case "einvoice": return <Einvoice />;
    case "einvoice-detail": return <EinvoiceDetail />;
    case "finance": return <Finance />;
    case "audit": return <Audit />;
    case "approvals": return <Approvals />;
    case "ingestion": return <Ingestion />;
    default: return <Landing />;
  }
}

export default function App() {
  return (
    <ThemeProvider>
      <I18nProvider>
        <AppStateProvider>
          <AuthProvider>
            <UiChromeProvider>
              <Screens />
              <AskDrawer />
              <QuickActionsPalette />
            </UiChromeProvider>
          </AuthProvider>
          <GlobalThemeToggle />
        </AppStateProvider>
      </I18nProvider>
    </ThemeProvider>
  );
}
