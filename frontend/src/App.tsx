import { lazy, Suspense, useEffect } from "react";
import { AuthProvider, useAuth } from "./auth/AuthProvider";
import { AppStateProvider, useAppState } from "./lib/appState";
import { I18nProvider } from "./lib/i18n";
import { ThemeProvider } from "./lib/theme";
import { UiChromeProvider } from "./lib/uiChrome";
import { AskDrawer } from "./components/AskDrawer";
import { QuickActionsPalette } from "./components/QuickActionsPalette";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { LogoMark } from "./components/Logo";

// Route-level code splitting: a visitor to the marketing landing page
// shouldn't have to download the chat interface, invoice forms, and
// finance charts before the page they actually asked for can render.
const Landing = lazy(() => import("./screens/Landing"));
const Login = lazy(() => import("./screens/Login"));
const Signup = lazy(() => import("./screens/Signup"));
const Onboarding = lazy(() => import("./screens/Onboarding"));
const Security = lazy(() => import("./screens/Security"));
const Legal = lazy(() => import("./screens/Legal"));
const Home = lazy(() => import("./screens/Home"));
const Agents = lazy(() => import("./screens/Agents"));
const Customers = lazy(() => import("./screens/Customers"));
const Einvoice = lazy(() => import("./screens/Einvoice"));
const EinvoiceDetail = lazy(() => import("./screens/EinvoiceDetail"));
const Finance = lazy(() => import("./screens/Finance"));
const Audit = lazy(() => import("./screens/Audit"));
const Approvals = lazy(() => import("./screens/Approvals"));
const Ingestion = lazy(() => import("./screens/Ingestion"));
const Settings = lazy(() => import("./screens/Settings"));

function Screens() {
  const { screen, show, setAskRole } = useAppState();
  const { identity, loading } = useAuth();
  const isPublic = ["landing", "login", "signup", "security", "legal"].includes(screen);

  useEffect(() => {
    if (identity) setAskRole(identity.role);
  }, [identity, setAskRole]);

  useEffect(() => {
    if (!loading && !identity && !isPublic) show("login");
    if (!loading && identity && (screen === "login" || screen === "signup")) show("home");
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
    case "home": return <Home />;
    case "agents": return <Agents />;
    case "customers": return <Customers />;
    case "einvoice": return <Einvoice />;
    case "einvoice-detail": return <EinvoiceDetail />;
    case "finance": return <Finance />;
    case "audit": return <Audit />;
    case "approvals": return <Approvals />;
    case "ingestion": return <Ingestion />;
    case "settings": return <Settings />;
    default: return <Landing />;
  }
}

const RouteFallback = (
  <div className="fb-route-loading">
    <div className="fb-route-loading-mark"><LogoMark large /></div>
    <div className="fb-route-loading-spinner" aria-hidden="true" />
  </div>
);

export default function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <I18nProvider>
          <AppStateProvider>
            <AuthProvider>
              <UiChromeProvider>
                <Suspense fallback={RouteFallback}>
                  <Screens />
                </Suspense>
                <AskDrawer />
                <QuickActionsPalette />
              </UiChromeProvider>
            </AuthProvider>
          </AppStateProvider>
        </I18nProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}
