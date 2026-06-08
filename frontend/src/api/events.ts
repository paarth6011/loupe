import { BASE_URL, getToken } from "./client";

export type ChangeEvent = {
  samples: number;
  alerts: number;
  open_alerts: number;
};

/**
 * Open the live-update stream. The server pushes a `changed` event whenever new
 * data lands (samples or alerts); the caller refetches in response, replacing
 * fixed-interval polling.
 *
 * EventSource can't send an Authorization header, so the JWT goes in the query
 * string (the backend validates it the same way). The browser auto-reconnects
 * after transient drops and after the server's periodic connection recycle; a
 * terminal failure (e.g. a rejected token) closes the stream, which we surface
 * via `onAuthError`. Returns an unsubscribe function.
 */
export function openEventStream(
  onChange: (e: ChangeEvent) => void,
  onAuthError: () => void,
): () => void {
  const token = getToken();
  if (!token) {
    onAuthError();
    return () => {};
  }

  const url = `${BASE_URL}/events?token=${encodeURIComponent(token)}`;
  const source = new EventSource(url);

  source.addEventListener("changed", (ev) => {
    try {
      onChange(JSON.parse((ev as MessageEvent).data) as ChangeEvent);
    } catch {
      // Ignore a malformed payload; the next event will refresh anyway.
    }
  });

  source.onerror = () => {
    // CLOSED means the server rejected the connection (bad/expired token) and
    // the browser won't retry — treat it as an auth failure. CONNECTING means a
    // transient drop the browser is already retrying, so leave it alone.
    if (source.readyState === EventSource.CLOSED) {
      onAuthError();
    }
  };

  return () => source.close();
}
