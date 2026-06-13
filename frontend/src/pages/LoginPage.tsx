import { useState, type FormEvent } from "react";

import {
  login,
  sendPasswordReset,
  signInWithPassword,
  signUpWithPassword,
} from "../api/auth";
import { isSupabaseMode } from "../api/supabase";

export default function LoginPage({ onLogin }: { onLogin: () => void }) {
  // One component, two auth modes (see api/supabase.ts). Self-host gets the
  // single-admin username/password form; the hosted SaaS gets Supabase
  // email/password sign-up + sign-in.
  return isSupabaseMode ? (
    <SupabaseLogin onLogin={onLogin} />
  ) : (
    <AdminLogin onLogin={onLogin} />
  );
}

// --- Self-host: single-admin login -----------------------------------------

function AdminLogin({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      onLogin();
    } catch {
      setError("Invalid credentials");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <h1>🔎 Loupe</h1>
        <p className="muted">Sign in to your observability dashboard</p>
        <label>
          Username
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>
        {error ? <div className="error-banner">{error}</div> : null}
        <button type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}

// --- Hosted SaaS: Supabase email/password ----------------------------------

type Mode = "signin" | "signup";

function SupabaseLogin({ onLogin }: { onLogin: () => void }) {
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (mode === "signup") {
        const { needsConfirmation } = await signUpWithPassword(email, password);
        if (needsConfirmation) {
          // Email confirmation is on: no session yet. Tell them to check email;
          // the auth listener in App flips to the dashboard once confirmed.
          setNotice("Check your email to confirm your account, then sign in.");
          setMode("signin");
          return;
        }
        // Instant signup (confirmation off): the session lands and the auth
        // listener takes over — but call onLogin too so we don't flash the form.
        onLogin();
      } else {
        await signInWithPassword(email, password);
        onLogin();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setBusy(false);
    }
  }

  async function resetPassword() {
    if (!email) {
      setError("Enter your email first, then click reset.");
      return;
    }
    setError(null);
    setNotice(null);
    try {
      await sendPasswordReset(email);
      setNotice("Password reset email sent — check your inbox.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not send reset email",
      );
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <h1>🔎 Loupe</h1>
        <p className="muted">
          {mode === "signin"
            ? "Sign in to your observability dashboard"
            : "Create your Loupe account"}
        </p>
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={
              mode === "signin" ? "current-password" : "new-password"
            }
            required
          />
        </label>
        {error ? <div className="error-banner">{error}</div> : null}
        {notice ? <div className="notice-banner">{notice}</div> : null}
        <button type="submit" disabled={busy}>
          {busy
            ? mode === "signin"
              ? "Signing in…"
              : "Creating account…"
            : mode === "signin"
              ? "Sign in"
              : "Create account"}
        </button>
        <div className="login-links">
          <button
            type="button"
            className="link-button"
            onClick={() => {
              setMode((m) => (m === "signin" ? "signup" : "signin"));
              setError(null);
              setNotice(null);
            }}
          >
            {mode === "signin"
              ? "Need an account? Sign up"
              : "Have an account? Sign in"}
          </button>
          {mode === "signin" ? (
            <button
              type="button"
              className="link-button"
              onClick={resetPassword}
            >
              Forgot password?
            </button>
          ) : null}
        </div>
      </form>
    </div>
  );
}
