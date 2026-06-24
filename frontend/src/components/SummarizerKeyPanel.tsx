import { useEffect, useState } from "react";

import { getSummarizerKey, updateSummarizerKey } from "../api/summarizer";

export default function SummarizerKeyPanel({
  onClose,
  onError,
}: {
  onClose: () => void;
  onError: (e: unknown) => void;
}) {
  const [key, setKey] = useState("");
  // Server state: whether a key is set, and the masked last-4 hint.
  const [saved, setSaved] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getSummarizerKey()
      .then((s) => {
        if (!active) return;
        setSaved(s.gemini_key_set);
        setHint(s.gemini_key_hint);
      })
      .catch(onError)
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [onError]);

  async function persist(next: string | null) {
    setSaving(true);
    setSaveError(null);
    try {
      const result = await updateSummarizerKey(next);
      setSaved(result.gemini_key_set);
      setHint(result.gemini_key_hint);
      setKey("");
    } catch {
      // 422 = the server's light format check; show it inline.
      setSaveError(
        "That doesn't look like a Gemini API key. Copy it from " +
          "aistudio.google.com/apikey.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Incident summaries</h3>
          <button onClick={onClose}>Close</button>
        </div>
        <p className="muted modal-sub">
          Alerts get a one-line, plain-English summary written by Google's{" "}
          Gemini. Add your own{" "}
          <a
            href="https://aistudio.google.com/apikey"
            target="_blank"
            rel="noreferrer"
          >
            free Gemini API key
          </a>{" "}
          — it's used <strong>only</strong> for these summaries. With no key,
          alerts still fire with a plain template summary.
        </p>

        {saved ? (
          <p className="muted notif-hint">
            A key is set (ends ···{hint}). Summaries use Gemini.
          </p>
        ) : null}

        <div className="key-create">
          <input
            type="password"
            autoComplete="off"
            placeholder={
              saved ? "Replace key (AIza…)" : "Paste your key (AIza…)"
            }
            value={key}
            aria-label="Gemini API key"
            onChange={(e) => {
              setKey(e.target.value);
              setSaveError(null);
            }}
          />
          <button
            disabled={saving || loading || !key.trim()}
            onClick={() => persist(key.trim())}
          >
            {saving ? "…" : "Save"}
          </button>
        </div>

        {saveError ? <div className="error-banner">{saveError}</div> : null}

        {saved ? (
          <div className="notif-actions">
            <button
              className="danger"
              disabled={saving}
              onClick={() => persist(null)}
            >
              Remove key
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
