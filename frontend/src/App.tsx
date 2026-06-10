import { useEffect, useState } from "react";

import { devLogin } from "./api/auth";
import { clearToken, getToken } from "./api/client";
import DashboardPage from "./pages/DashboardPage";
import LoginPage from "./pages/LoginPage";
import StatusPage from "./pages/StatusPage";

// "checking" runs the one-shot dev auto-login probe before deciding whether to
// show the sign-in form, so a developer's machine skips the login screen while
// production (where /auth/dev-login 404s) falls straight through to it.
type Phase = "checking" | "authed" | "login";

export default function App() {
  // The public status page is reachable without logging in. A tiny path check
  // keeps us from pulling in a router for a single extra route.
  const isStatus = window.location.pathname.replace(/\/$/, "") === "/status";

  const [phase, setPhase] = useState<Phase>(() =>
    getToken() ? "authed" : "checking",
  );

  useEffect(() => {
    if (isStatus || phase !== "checking") return;
    let cancelled = false;
    devLogin().then((ok) => {
      if (!cancelled) setPhase(ok ? "authed" : "login");
    });
    return () => {
      cancelled = true;
    };
  }, [isStatus, phase]);

  if (isStatus) return <StatusPage />;

  if (phase === "checking") {
    return (
      <div className="login-wrap">
        <p className="muted">Loading…</p>
      </div>
    );
  }

  if (phase === "login") {
    return <LoginPage onLogin={() => setPhase("authed")} />;
  }

  return (
    <DashboardPage
      onLogout={() => {
        clearToken();
        // Show the sign-in form on explicit logout rather than silently
        // re-running dev auto-login (a refresh will auto-login again in dev).
        setPhase("login");
      }}
    />
  );
}
