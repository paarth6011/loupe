import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import SummarizerKeyPanel from "./SummarizerKeyPanel";
import { getSummarizerKey, updateSummarizerKey } from "../api/summarizer";

vi.mock("../api/summarizer", () => ({
  getSummarizerKey: vi.fn(),
  updateSummarizerKey: vi.fn(),
}));

const KEY = "AIzaSyA-fake-gemini-key-1234";

describe("SummarizerKeyPanel", () => {
  it("saves a pasted key (Save disabled until something is typed)", async () => {
    vi.mocked(getSummarizerKey).mockResolvedValue({
      gemini_key_set: false,
      gemini_key_hint: null,
    });
    vi.mocked(updateSummarizerKey).mockResolvedValue({
      gemini_key_set: true,
      gemini_key_hint: "1234",
    });

    render(<SummarizerKeyPanel onClose={vi.fn()} onError={vi.fn()} />);

    const input = await screen.findByLabelText(/gemini api key/i);
    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();

    fireEvent.change(input, { target: { value: KEY } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(updateSummarizerKey).toHaveBeenCalledWith(KEY));
    // After saving, the masked "key is set" state appears (last-4 only).
    expect(await screen.findByText(/ends ···1234/i)).toBeVisible();
  });

  it("shows the set state and clears the key on Remove", async () => {
    vi.mocked(getSummarizerKey).mockResolvedValue({
      gemini_key_set: true,
      gemini_key_hint: "1234",
    });
    vi.mocked(updateSummarizerKey).mockResolvedValue({
      gemini_key_set: false,
      gemini_key_hint: null,
    });

    render(<SummarizerKeyPanel onClose={vi.fn()} onError={vi.fn()} />);

    expect(await screen.findByText(/ends ···1234/i)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /remove key/i }));

    await waitFor(() => expect(updateSummarizerKey).toHaveBeenCalledWith(null));
  });

  it("shows an inline error when the key is rejected", async () => {
    vi.mocked(getSummarizerKey).mockResolvedValue({
      gemini_key_set: false,
      gemini_key_hint: null,
    });
    vi.mocked(updateSummarizerKey).mockRejectedValue(new Error("422"));

    render(<SummarizerKeyPanel onClose={vi.fn()} onError={vi.fn()} />);
    fireEvent.change(await screen.findByLabelText(/gemini api key/i), {
      target: { value: "short" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(
      await screen.findByText(/doesn't look like a gemini api key/i),
    ).toBeVisible();
  });
});
