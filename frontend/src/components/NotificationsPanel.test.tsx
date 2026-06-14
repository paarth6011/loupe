import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import NotificationsPanel from "./NotificationsPanel";
import {
  getNotificationSettings,
  sendTestNotification,
  updateNotificationSettings,
} from "../api/notifications";

vi.mock("../api/notifications", () => ({
  getNotificationSettings: vi.fn(),
  updateNotificationSettings: vi.fn(),
  sendTestNotification: vi.fn(),
}));

const SLACK = "https://hooks.slack.com/services/T/B/X";

describe("NotificationsPanel", () => {
  it("loads the saved webhook and saves an edited one", async () => {
    vi.mocked(getNotificationSettings).mockResolvedValue({ webhook_url: null });
    vi.mocked(updateNotificationSettings).mockResolvedValue({
      webhook_url: SLACK,
    });

    render(<NotificationsPanel onClose={vi.fn()} onError={vi.fn()} />);

    const input = await screen.findByLabelText(/webhook url/i);
    // Save is disabled until the field differs from what's saved.
    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();

    fireEvent.change(input, { target: { value: SLACK } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(updateNotificationSettings).toHaveBeenCalledWith(SLACK),
    );
  });

  it("blocks testing until edits are saved, then reports the result", async () => {
    vi.mocked(getNotificationSettings).mockResolvedValue({
      webhook_url: SLACK,
    });
    vi.mocked(sendTestNotification).mockResolvedValue({
      ok: true,
      detail: "Test notification sent.",
    });

    render(<NotificationsPanel onClose={vi.fn()} onError={vi.fn()} />);

    // With a saved URL and no edits, Send test is enabled.
    const testBtn = await screen.findByRole("button", { name: /send test/i });
    expect(testBtn).toBeEnabled();

    // Editing without saving disables the test button.
    fireEvent.change(screen.getByLabelText(/webhook url/i), {
      target: { value: SLACK + "x" },
    });
    expect(screen.getByRole("button", { name: /send test/i })).toBeDisabled();
    expect(screen.getByText(/save your changes before testing/i)).toBeVisible();

    // Revert the edit → test enabled again → success is shown.
    fireEvent.change(screen.getByLabelText(/webhook url/i), {
      target: { value: SLACK },
    });
    fireEvent.click(screen.getByRole("button", { name: /send test/i }));
    expect(await screen.findByText(/test notification sent/i)).toBeVisible();
  });

  it("shows an inline error when the URL is rejected", async () => {
    vi.mocked(getNotificationSettings).mockResolvedValue({ webhook_url: null });
    vi.mocked(updateNotificationSettings).mockRejectedValue(
      new Error("422 invalid"),
    );

    render(<NotificationsPanel onClose={vi.fn()} onError={vi.fn()} />);
    fireEvent.change(await screen.findByLabelText(/webhook url/i), {
      target: { value: "https://evil.example.com/x" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(
      await screen.findByText(/doesn't look like a slack or discord webhook/i),
    ).toBeVisible();
  });
});
