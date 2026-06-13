import { useState, type FormEvent } from "react";

import {
  login,
  sendPasswordReset,
  signInWithPassword,
  signUpWithPassword,
  updatePassword,
  verifyRecoveryCode,
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

type Mode = "signin" | "signup" | "forgot";

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

  if (mode === "forgot") {
    return (
      <ForgotPassword
        initialEmail={email}
        onBack={() => {
          setMode("signin");
          resetMessages();
        }}
        onDone={onLogin}
      />
    );
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
            <LinkButton
              onClick={() => {
                setMode("forgot");
                resetMessages();
              }}
            >
              Forgot password?
            </LinkButton>
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

// Password reset via a 6-digit CODE (not a magic link) — immune to the email
// link-prefetch that burns one-time tokens (see api/auth.ts). Step 1 emails the
// code; step 2 verifies it and sets the new password, leaving the user signed in.
function ForgotPassword({
  initialEmail,
  onBack,
  onDone,
}: {
  initialEmail: string;
  onBack: () => void;
  onDone: () => void;
}) {
  const [step, setStep] = useState<"request" | "reset">("request");
  const [email, setEmail] = useState(initialEmail);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function sendCode(e: FormEvent) {
    e.preventDefault();
    if (!email) {
      setError("Enter your email.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await sendPasswordReset(email);
      setStep("reset");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send the code");
    } finally {
      setBusy(false);
    }
  }

  async function doReset(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }
    setBusy(true);
    try {
      await verifyRecoveryCode(email, code.trim());
      await updatePassword(password);
      onDone();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Invalid or expired code — request a new one.",
      );
    } finally {
      setBusy(false);
    }
  }

  const back = <LinkButton onClick={onBack}>Back to sign in</LinkButton>;

  if (step === "request") {
    return (
      <AuthShell
        title="Reset your password"
        subtitle="Enter your email and we'll send you a reset code."
        footer={<div className="auth-links">{back}</div>}
      >
        <form className="auth-form" onSubmit={sendCode}>
          <TextField
            id="email"
            label="Email"
            type="email"
            value={email}
            onChange={setEmail}
            autoComplete="email"
          />
          {error ? <FormBanner kind="error">{error}</FormBanner> : null}
          <AuthButton busy={busy} busyLabel="Sending…">
            Send reset code
          </AuthButton>
        </form>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Enter your code"
      subtitle={`We sent a 6-digit code to ${email}. Enter it with your new password.`}
      footer={<div className="auth-links">{back}</div>}
    >
      <form className="auth-form" onSubmit={doReset}>
        <TextField
          id="code"
          label="Reset code"
          value={code}
          onChange={setCode}
          inputMode="numeric"
          autoComplete="one-time-code"
        />
        <PasswordField
          id="new-password"
          label="New password"
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
          hint="At least 6 characters."
        />
        <PasswordField
          id="confirm-password"
          label="Confirm password"
          value={confirm}
          onChange={setConfirm}
          autoComplete="new-password"
        />
        {error ? <FormBanner kind="error">{error}</FormBanner> : null}
        <AuthButton busy={busy} busyLabel="Resetting…">
          Reset password
        </AuthButton>
      </form>
    </AuthShell>
  );
}
