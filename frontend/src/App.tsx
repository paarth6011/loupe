import { useEffect, useState } from "react";

import { devLogin, logout } from "./api/auth";
import { getToken } from "./api/client";
import { isSupabaseMode, supabase } from "./api/supabase";
import DashboardPage from "./pages/DashboardPage";
import LoginPage from "./pages/LoginPage";
import ResetPasswordPage from "./pages/ResetPasswordPage";
import StatusPage from "./pages/StatusPage";

// "checking" runs the initial auth probe (a dev auto-login attempt in admin
// mode, or restoring a persisted Supabase session) before deciding whether to
// show the sign-in form. "recovery" is the post-reset-link "set new password"
// screen.
type Phase = "checking" | "authed" | "login" | "recovery";

export default function App() {
  // The public status page is reachable without logging in. A tiny path check
  // keeps us from pulling in a router for a single extra route.
  const isStatus = window.location.pathname.replace(/\/$/, "") === "/status";

  const [phase, setPhase] = useState<Phase>(() => {
    if (isSupabaseMode) return "checking"; // resolved by getSession() below
    return getToken() ? "authed" : "checking";
  });
  // Admin mode only: whether this is a dev box (where /auth/dev-login succeeds
  // and login is skipped). In dev there is nothing to log out of, so the
  // dashboard hides its "Log out" button. Always false in supabase mode, where
  // sign-out is real.
  const [devMode, setDevMode] = useState(false);

  // Admin mode: probe dev-login on mount. It both decides whether to skip the
  // sign-in form (when we have no token yet) and tells us if this is a dev box.
  // In dev it returns a token; in production it 404s and we fall through.
  useEffect(() => {
    if (isStatus || isSupabaseMode) return;
    let cancelled = false;
    devLogin().then((ok) => {
      if (cancelled) return;
      setDevMode(ok);
      setPhase((p) => (p === "checking" ? (ok ? "authed" : "login") : p));
    });
    return () => {
      cancelled = true;
    };
  }, [isStatus]);

  // Supabase mode: gate on the Supabase session. getSession() restores a
  // persisted login on reload; onAuthStateChange keeps us in sync with
  // sign-in / sign-out / token-refresh happening anywhere in the app.
  useEffect(() => {
    if (isStatus || !isSupabaseMode || !supabase) return;
    let cancelled = false;
    // A password-reset link returns here with `type=recovery` in the URL hash.
    const isRecovery = window.location.hash.includes("type=recovery");
    supabase.auth.getSession().then(({ data }) => {
      if (cancelled) return;
      if (isRecovery) setPhase("recovery");
      else setPhase(data.session ? "authed" : "login");
    });
    const { data: sub } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === "PASSWORD_RECOVERY") {
        setPhase("recovery");
        return;
      }
      // Stay on the reset screen until the user finishes it — the SIGNED_IN that
      // fires when the recovery session is established must not skip past it.
      setPhase((prev) =>
        prev === "recovery" ? "recovery" : session ? "authed" : "login",
      );
    });
    return () => {
      cancelled = true;
      sub.subscription.unsubscribe();
    };
  }, [isStatus]);

  if (isStatus) return <StatusPage />;

  if (phase === "checking") {
    return (
      <div className="auth-wrap">
        <p className="muted">Loading…</p>
      </div>
    );
  }

  if (phase === "recovery") {
    return <ResetPasswordPage onDone={() => setPhase("authed")} />;
  }

  if (phase === "login") {
    return <LoginPage onLogin={() => setPhase("authed")} />;
  }

  return (
    <DashboardPage
      // Supabase mode always has a real session to end; admin dev boxes skip
      // login entirely, so there's nothing to log out of there.
      showLogout={isSupabaseMode || !devMode}
      onLogout={() => {
        // signOut() for the active mode, then show the sign-in form. (In
        // supabase mode onAuthStateChange would also flip us to "login".)
        void logout().then(() => setPhase("login"));
      }}
    />
  );
}
