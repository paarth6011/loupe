import { useEffect, useState, type FormEvent } from "react";

import {
  login,
  sendPasswordReset,
  setRecoveryInProgress,
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
  OtpInput,
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
// link-prefetch that burns one-time tokens (see api/auth.ts). Three steps:
// (1) email the code, (2) verify the code, then — only once it's accepted —
// (3) set the new password. Verifying first means the user never types a new
// password against a wrong/expired code.
function ForgotPassword({
  initialEmail,
  onBack,
  onDone,
}: {
  initialEmail: string;
  onBack: () => void;
  onDone: () => void;
}) {
  const [step, setStep] = useState<"request" | "code" | "password">("request");
  const [email, setEmail] = useState(initialEmail);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Throttle "Resend": a countdown gates the link so a user can't fire off a
  // burst of code emails (each one invalidates the previous, and they cost us).
  const [cooldown, setCooldown] = useState(0);

  // Verifying the code establishes a recovery session; flag it so App's auth
  // listener doesn't bounce us to the dashboard before the password is set.
  useEffect(() => {
    setRecoveryInProgress(true);
    return () => setRecoveryInProgress(false);
  }, []);

  // Tick the resend cooldown down to zero, one second at a time.
  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

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
      setStep("code");
      setCooldown(30);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send the code");
    } finally {
      setBusy(false);
    }
  }

  // Re-send the code from the entry screen. Gated by the cooldown so it can't be
  // spammed; on success we restart the timer and confirm via an aria-live notice.
  async function resend() {
    if (cooldown > 0 || busy) return;
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      await sendPasswordReset(email);
      setCode("");
      setNotice("We sent a new code — check your inbox.");
      setCooldown(30);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not resend the code",
      );
    } finally {
      setBusy(false);
    }
  }

  async function verifyCode(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    if (!code.trim()) {
      setError("Enter the 6-digit code from your email.");
      return;
    }
    setBusy(true);
    try {
      await verifyRecoveryCode(email, code.trim());
      setStep("password");
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

  async function setNewPassword(e: FormEvent) {
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
      await updatePassword(password);
      onDone();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not update password",
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

  if (step === "code") {
    return (
      <AuthShell
        title="Enter your code"
        subtitle={`We sent a 6-digit code to ${email}. Enter it to continue.`}
        footer={<div className="auth-links">{back}</div>}
      >
        <form className="auth-form" onSubmit={verifyCode}>
          <OtpInput
            id="code"
            label="Verification code"
            value={code}
            onChange={setCode}
          />
          {error ? <FormBanner kind="error">{error}</FormBanner> : null}
          {notice ? <FormBanner kind="notice">{notice}</FormBanner> : null}
          <AuthButton busy={busy} busyLabel="Verifying…">
            Verify code
          </AuthButton>
          <p className="auth-resend">
            Didn't receive a code?{" "}
            {cooldown > 0 ? (
              <span className="auth-resend-wait">Resend in {cooldown}s</span>
            ) : (
              <LinkButton onClick={resend}>Resend</LinkButton>
            )}
          </p>
        </form>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Set a new password"
      subtitle="Your code is verified — choose a new password."
      footer={<div className="auth-links">{back}</div>}
    >
      <form className="auth-form" onSubmit={setNewPassword}>
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
