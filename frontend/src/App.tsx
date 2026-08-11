import { AppStateProvider, useAppState } from "./lib/appState";
import { I18nProvider } from "./lib/i18n";
import { ThemeProvider, ThemeToggleButton } from "./lib/theme";

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

function Screens() {
  const { screen } = useAppState();

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
    default: return <Landing />;
  }
}

export default function App() {
  return (
    <ThemeProvider>
      <I18nProvider>
        <AppStateProvider>
          <Screens />
          <ThemeToggleButton />
        </AppStateProvider>
      </I18nProvider>
    </ThemeProvider>
  );
}
