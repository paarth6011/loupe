import { apiFetch } from "./client";
import type { SummarizerKeySettings } from "../types";

export function getSummarizerKey(): Promise<SummarizerKeySettings> {
  return apiFetch<SummarizerKeySettings>("/summarizer/key");
}

// Pass null to clear the key (summaries fall back to the $0 template).
export function updateSummarizerKey(
  geminiApiKey: string | null,
): Promise<SummarizerKeySettings> {
  return apiFetch<SummarizerKeySettings>("/summarizer/key", {
    method: "PUT",
    body: JSON.stringify({ gemini_api_key: geminiApiKey }),
  });
}
