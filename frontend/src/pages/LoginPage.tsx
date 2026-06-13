import { useState, type FormEvent } from "react";

import {
  login,
  sendPasswordReset,
  signInWithPassword,
  signUpWithPassword,
} from "../api/auth";
import { isSupabaseMode } from "../api/supabase";
import {
  AuthButton,
  AuthShell,
  FormBanner,
  LinkButton,
  PasswordField,
  TextField,
} from "../components/authUi";

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
    <AuthShell title="Welcome back" subtitle="Sign in to your dashboard">
      <form className="auth-form" onSubmit={submit}>
        <TextField
          id="username"
          label="Username"
          value={username}
          onChange={setUsername}
          autoComplete="username"
        />
        <PasswordField
          id="password"
          label="Password"
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
        />
        {error ? <FormBanner kind="error">{error}</FormBanner> : null}
        <AuthButton busy={busy} busyLabel="Signing in…">
          Sign in
        </AuthButton>
      </form>
    </AuthShell>
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

  function resetMessages() {
    setError(null);
    setNotice(null);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    resetMessages();
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
    resetMessages();
    try {
      await sendPasswordReset(email);
      setNotice("Password reset email sent — check your inbox.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not send reset email",
      );
    }
  }

  const isSignin = mode === "signin";

  return (
    <AuthShell
      title={isSignin ? "Welcome back" : "Create your account"}
      subtitle={
        isSignin
          ? "Sign in to your observability dashboard"
          : "Start monitoring your AI workloads in minutes"
      }
      footer={
        <div className="auth-links">
          <LinkButton
            onClick={() => {
              setMode(isSignin ? "signup" : "signin");
              resetMessages();
            }}
          >
            {isSignin ? "Need an account? Sign up" : "Have an account? Sign in"}
          </LinkButton>
          {isSignin ? (
            <LinkButton onClick={resetPassword}>Forgot password?</LinkButton>
          ) : null}
        </div>
      }
    >
      <form className="auth-form" onSubmit={submit}>
        <TextField
          id="email"
          label="Email"
          type="email"
          value={email}
          onChange={setEmail}
          autoComplete="email"
        />
        <PasswordField
          id="password"
          label="Password"
          value={password}
          onChange={setPassword}
          autoComplete={isSignin ? "current-password" : "new-password"}
          hint={isSignin ? undefined : "At least 6 characters."}
        />
        {error ? <FormBanner kind="error">{error}</FormBanner> : null}
        {notice ? <FormBanner kind="notice">{notice}</FormBanner> : null}
        <AuthButton
          busy={busy}
          busyLabel={isSignin ? "Signing in…" : "Creating account…"}
        >
          {isSignin ? "Sign in" : "Create account"}
        </AuthButton>
      </form>
    </AuthShell>
  );
}
