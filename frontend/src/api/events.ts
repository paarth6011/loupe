import { apiFetch, ApiError, BASE_URL } from "./client";

export type ChangeEvent = {
  samples: number;
  alerts: number;
  open_alerts: number;
};

type StreamTicket = { ticket: string };

/**
 * Open the live-update stream. The server pushes a `changed` event whenever new
 * data lands (samples or alerts); the caller refetches in response, replacing
 * fixed-interval polling.
 *
 * EventSource can't send an Authorization header, so instead of putting the full
 * admin JWT in the URL we first exchange it (via the normal bearer request) for
 * a short-lived, read-only *stream ticket* and pass that in the query string.
 * Tickets expire quickly, so we manage reconnection ourselves: on any drop we
 * close the source and reconnect with a freshly-minted ticket. A 401 when
 * minting (admin token expired/invalid) is terminal and surfaces via
 * `onAuthError`. Returns an unsubscribe function.
 */
export function openEventStream(
  onChange: (e: ChangeEvent) => void,
  onAuthError: () => void,
): () => void {
  let closed = false;
  let source: EventSource | null = null;
  let retry: ReturnType<typeof setTimeout> | null = null;

  async function connect(): Promise<void> {
    if (closed) return;
    let ticket: string;
    try {
      ticket = (
        await apiFetch<StreamTicket>("/auth/stream-ticket", { method: "POST" })
      ).ticket;
    } catch (err) {
      // A rejected admin token is terminal; anything else is transient.
      if (err instanceof ApiError && err.status === 401) {
        onAuthError();
        return;
      }
      retry = setTimeout(connect, 3000);
      return;
    }
    if (closed) return;

    const url = `${BASE_URL}/events?ticket=${encodeURIComponent(ticket)}`;
    source = new EventSource(url);

    source.addEventListener("changed", (ev) => {
      try {
        onChange(JSON.parse((ev as MessageEvent).data) as ChangeEvent);
      } catch {
        // Ignore a malformed payload; the next event will refresh anyway.
      }
    });

    source.onerror = () => {
      // The ticket may have expired or the server recycled the connection.
      // Drop this source and reconnect with a fresh ticket rather than letting
      // the browser retry the now-stale ticket in the URL.
      source?.close();
      source = null;
      if (!closed) retry = setTimeout(connect, 1000);
    };
  }

  void connect();

  return () => {
    closed = true;
    if (retry) clearTimeout(retry);
    source?.close();
  };
}
