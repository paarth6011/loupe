import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import LoginPage from "./LoginPage";
import {
  sendPasswordReset,
  signInWithPassword,
  signUpWithPassword,
  updatePassword,
  verifyRecoveryCode,
} from "../api/auth";

// Drive the component down its Supabase branch and stub the auth calls so the
// test exercises the form logic, not Supabase itself.
vi.mock("../api/supabase", () => ({ isSupabaseMode: true, supabase: null }));
vi.mock("../api/auth", () => ({
  login: vi.fn(),
  signInWithPassword: vi.fn().mockResolvedValue(undefined),
  signUpWithPassword: vi.fn().mockResolvedValue({ needsConfirmation: false }),
  sendPasswordReset: vi.fn().mockResolvedValue(undefined),
  verifyRecoveryCode: vi.fn().mockResolvedValue(undefined),
  updatePassword: vi.fn().mockResolvedValue(undefined),
}));

afterEach(() => vi.clearAllMocks());

function fill(label: RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

describe("LoginPage (Supabase mode)", () => {
  it("signs in with email + password and notifies the parent", async () => {
    const onLogin = vi.fn();
    render(<LoginPage onLogin={onLogin} />);

    fill(/email/i, "user@example.com");
    fill(/^password$/i, "hunter2");
    fireEvent.click(screen.getByRole("button", { name: /^sign in$/i }));

    await waitFor(() =>
      expect(signInWithPassword).toHaveBeenCalledWith(
        "user@example.com",
        "hunter2",
      ),
    );
    expect(onLogin).toHaveBeenCalled();
  });

  it("toggles to sign-up and shows the confirmation notice when required", async () => {
    vi.mocked(signUpWithPassword).mockResolvedValueOnce({
      needsConfirmation: true,
    });
    const onLogin = vi.fn();
    render(<LoginPage onLogin={onLogin} />);

    fireEvent.click(screen.getByRole("button", { name: /sign up/i }));
    expect(
      screen.getByRole("button", { name: /create account/i }),
    ).toBeInTheDocument();

    fill(/email/i, "new@example.com");
    fill(/^password$/i, "hunter2");
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() =>
      expect(screen.getByText(/check your email/i)).toBeInTheDocument(),
    );
    // Email not yet confirmed → no session → parent must NOT be told we're in.
    expect(onLogin).not.toHaveBeenCalled();
  });

  it("resets the password with an emailed code (no magic link)", async () => {
    const onLogin = vi.fn();
    render(<LoginPage onLogin={onLogin} />);

    // The email typed on the sign-in form carries into the reset flow.
    fill(/email/i, "user@example.com");
    fireEvent.click(screen.getByRole("button", { name: /forgot password/i }));

    // Step 1: request the code.
    fireEvent.click(screen.getByRole("button", { name: /send reset code/i }));
    const codeField = await screen.findByLabelText(/reset code/i);
    expect(sendPasswordReset).toHaveBeenCalledWith("user@example.com");

    // Step 2: enter the code + new password.
    fireEvent.change(codeField, { target: { value: "123456" } });
    fill(/new password/i, "hunter2");
    fill(/confirm password/i, "hunter2");
    fireEvent.click(screen.getByRole("button", { name: /reset password/i }));

    await waitFor(() =>
      expect(verifyRecoveryCode).toHaveBeenCalledWith(
        "user@example.com",
        "123456",
      ),
    );
    expect(updatePassword).toHaveBeenCalledWith("hunter2");
    await waitFor(() => expect(onLogin).toHaveBeenCalled());
  });
});
