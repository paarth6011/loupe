import { useEffect, useState } from "react";

import { createApiKey, listApiKeys, revokeApiKey } from "../api/apikeys";
import type { ApiKey, ApiKeyCreated } from "../types";

function when(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : "never";
}

export default function ApiKeysPanel({
  onClose,
  onError,
}: {
  onClose: () => void;
  onError: (e: unknown) => void;
}) {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  // The one-time plaintext for a freshly created key (shown until dismissed).
  const [fresh, setFresh] = useState<ApiKeyCreated | null>(null);
  const [copied, setCopied] = useState(false);

  function refresh() {
    listApiKeys().then(setKeys).catch(onError);
  }

  useEffect(() => {
    let active = true;
    listApiKeys()
      .then((k) => {
        if (active) setKeys(k);
      })
      .catch(onError);
    return () => {
      active = false;
    };
  }, [onError]);

  async function create() {
    if (!name.trim()) return;
    setCreating(true);
    try {
      const created = await createApiKey(name.trim());
      setFresh(created);
      setCopied(false);
      setName("");
      refresh();
    } catch (e) {
      onError(e);
    } finally {
      setCreating(false);
    }
  }

  async function revoke(id: number) {
    try {
      await revokeApiKey(id);
      refresh();
    } catch (e) {
      onError(e);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>API keys</h3>
          <button onClick={onClose}>Close</button>
        </div>
        <p className="muted modal-sub">
          Per-source ingestion keys for <code>POST /metrics</code> — give each
          app its own, and revoke it without touching the others. Set it as{" "}
          <code>LOUPE_API_KEY</code> for the SDK.
        </p>

        {fresh ? (
          <div className="key-reveal">
            <div className="key-reveal-label">
              Copy <strong>{fresh.name}</strong> now — it won't be shown again:
            </div>
            <div className="key-reveal-row">
              <code className="key-value">{fresh.key}</code>
              <button
                onClick={() => {
                  navigator.clipboard?.writeText(fresh.key);
                  setCopied(true);
                }}
              >
                {copied ? "Copied" : "Copy"}
              </button>
              <button className="secondary" onClick={() => setFresh(null)}>
                Done
              </button>
            </div>
          </div>
        ) : null}

        <div className="key-create">
          <input
            type="text"
            placeholder="Key name (e.g. support-bot prod)"
            value={name}
            aria-label="new key name"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()}
          />
          <button disabled={!name.trim() || creating} onClick={create}>
            {creating ? "…" : "Create key"}
          </button>
        </div>

        <table className="keys-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Prefix</th>
              <th>Last used</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {keys.length === 0 ? (
              <tr>
                <td colSpan={4} className="muted">
                  No keys yet.
                </td>
              </tr>
            ) : (
              keys.map((k) => (
                <tr key={k.id}>
                  <td>{k.name}</td>
                  <td>
                    <code>{k.prefix}…</code>
                  </td>
                  <td className="muted">{when(k.last_used_at)}</td>
                  <td>
                    <button className="danger" onClick={() => revoke(k.id)}>
                      Revoke
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
