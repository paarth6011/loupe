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
  // Whether this is a dev box (where /auth/dev-login succeeds and login is
  // skipped). In dev there is nothing to log out of, so the dashboard hides its
  // "Log out" button. Stays false in production, where login is real.
  const [devMode, setDevMode] = useState(false);

  useEffect(() => {
    if (isStatus) return;
    let cancelled = false;
    // Probe dev-login on mount: it both decides whether to skip the sign-in
    // form (when we have no token yet) and tells us if this is a dev box. In
    // dev it returns a token; in production it 404s and we fall through.
    devLogin().then((ok) => {
      if (cancelled) return;
      setDevMode(ok);
      setPhase((p) => (p === "checking" ? (ok ? "authed" : "login") : p));
    });
    return () => {
      cancelled = true;
    };
  }, [isStatus]);

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
      // Dev boxes skip login entirely, so there's nothing to log out of — hide
      // the button there and only show it on a real (production) login.
      showLogout={!devMode}
      onLogout={() => {
        clearToken();
        // Show the sign-in form on explicit logout rather than silently
        // re-running dev auto-login (a refresh will auto-login again in dev).
        setPhase("login");
      }}
    />
  );
}
