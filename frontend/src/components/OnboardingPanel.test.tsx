import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import OnboardingPanel from "./OnboardingPanel";
import { createApiKey } from "../api/apikeys";

vi.mock("../api/client", () => ({ BASE_URL: "https://api.getloupe.net" }));
vi.mock("../api/apikeys", () => ({ createApiKey: vi.fn() }));

describe("OnboardingPanel", () => {
  it("pre-fills the SDK snippet with the live API URL", () => {
    render(<OnboardingPanel onError={vi.fn()} />);
    // The install snippet should point the SDK at this backend.
    expect(
      screen.getByText(/LOUPE_URL=https:\/\/api\.getloupe\.net/),
    ).toBeInTheDocument();
    expect(screen.getByText(/from loupe import track/)).toBeInTheDocument();
  });

  it("creates a key and reveals the plaintext once", async () => {
    vi.mocked(createApiKey).mockResolvedValue({
      id: 1,
      name: "my-app",
      prefix: "loupe_sk_abc",
      key: "loupe_sk_abc123secret",
      created_at: "2026-06-14T00:00:00Z",
      last_used_at: null,
    });

    render(<OnboardingPanel onError={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /create key/i }));

    await waitFor(() => expect(createApiKey).toHaveBeenCalledWith("my-app"));
    // The one-time plaintext is shown after creation.
    expect(
      await screen.findByText("loupe_sk_abc123secret"),
    ).toBeInTheDocument();
  });
});
