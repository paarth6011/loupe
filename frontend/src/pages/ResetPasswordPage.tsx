import { useState, type FormEvent } from "react";

import { updatePassword } from "../api/auth";
import {
  AuthButton,
  AuthShell,
  FormBanner,
  PasswordField,
} from "../components/authUi";

/**
 * Shown when the user returns from a Supabase password-reset link (the
 * PASSWORD_RECOVERY flow — see App.tsx). They're holding a short-lived recovery
 * session; we let them set a new password, then hand them to the dashboard.
 */
export default function ResetPasswordPage({ onDone }: { onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
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
      // Strip the recovery token from the URL so a refresh doesn't re-trigger
      // the flow, then continue to the (now authenticated) dashboard.
      window.history.replaceState(null, "", window.location.pathname);
      onDone();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not update password",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="Set a new password"
      subtitle="Choose a new password for your account."
    >
      <form className="auth-form" onSubmit={submit}>
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
        <AuthButton busy={busy} busyLabel="Updating…">
          Update password
        </AuthButton>
      </form>
    </AuthShell>
  );
}
