import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ResetPasswordPage from "./ResetPasswordPage";
import { updatePassword } from "../api/auth";

vi.mock("../api/auth", () => ({
  updatePassword: vi.fn().mockResolvedValue(undefined),
}));

afterEach(() => vi.clearAllMocks());

function fill(label: RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

describe("ResetPasswordPage", () => {
  it("rejects mismatched passwords without calling the API", () => {
    render(<ResetPasswordPage onDone={vi.fn()} />);
    fill(/new password/i, "hunter2");
    fill(/confirm password/i, "different");
    fireEvent.click(screen.getByRole("button", { name: /update password/i }));
    expect(screen.getByText(/don't match/i)).toBeInTheDocument();
    expect(updatePassword).not.toHaveBeenCalled();
  });

  it("rejects a too-short password", () => {
    render(<ResetPasswordPage onDone={vi.fn()} />);
    fill(/new password/i, "abc");
    fill(/confirm password/i, "abc");
    fireEvent.click(screen.getByRole("button", { name: /update password/i }));
    // "must be at least 6" is the error (distinct from the always-on hint text).
    expect(screen.getByText(/must be at least 6/i)).toBeInTheDocument();
    expect(updatePassword).not.toHaveBeenCalled();
  });

  it("updates the password and calls onDone on success", async () => {
    const onDone = vi.fn();
    render(<ResetPasswordPage onDone={onDone} />);
    fill(/new password/i, "hunter2");
    fill(/confirm password/i, "hunter2");
    fireEvent.click(screen.getByRole("button", { name: /update password/i }));
    await waitFor(() => expect(updatePassword).toHaveBeenCalledWith("hunter2"));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });
});
