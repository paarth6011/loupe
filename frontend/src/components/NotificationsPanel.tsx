import { useEffect, useState } from "react";

import {
  getNotificationSettings,
  sendTestNotification,
  updateNotificationSettings,
} from "../api/notifications";
import type { NotificationTestResult } from "../types";

export default function NotificationsPanel({
  onClose,
  onError,
}: {
  onClose: () => void;
  onError: (e: unknown) => void;
}) {
  const [url, setUrl] = useState("");
  // The last value persisted on the server (null when no channel is set).
  const [saved, setSaved] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [test, setTest] = useState<NotificationTestResult | null>(null);

  useEffect(() => {
    let active = true;
    getNotificationSettings()
      .then((s) => {
        if (!active) return;
        setSaved(s.webhook_url);
        setUrl(s.webhook_url ?? "");
      })
      .catch(onError)
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [onError]);

  // The test sends to the *saved* URL, so unsaved edits must be saved first.
  const dirty = url.trim() !== (saved ?? "");

  async function persist(next: string | null) {
    setSaving(true);
    setSaveError(null);
    setTest(null);
    try {
      const result = await updateNotificationSettings(next);
      setSaved(result.webhook_url);
      setUrl(result.webhook_url ?? "");
    } catch {
      // 422 = the server's URL validation; show it inline, not as a global error.
      setSaveError(
        "That doesn't look like a Slack or Discord webhook. Use an https:// " +
          "URL from hooks.slack.com or discord.com.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function runTest() {
    setTesting(true);
    setTest(null);
    try {
      setTest(await sendTestNotification());
    } catch (e) {
      onError(e);
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Notifications</h3>
          <button onClick={onClose}>Close</button>
        </div>
        <p className="muted modal-sub">
          Send alerts to your team's Slack or Discord when they fire and
          resolve. Paste an{" "}
          <a
            href="https://api.slack.com/messaging/webhooks"
            target="_blank"
            rel="noreferrer"
          >
            incoming webhook
          </a>{" "}
          URL from Slack, or a{" "}
          <a
            href="https://support.discord.com/hc/en-us/articles/228383668"
            target="_blank"
            rel="noreferrer"
          >
            Discord webhook
          </a>
          .
        </p>

        <div className="key-create">
          <input
            type="url"
            inputMode="url"
            placeholder="https://hooks.slack.com/services/…"
            value={url}
            aria-label="Slack or Discord webhook URL"
            onChange={(e) => {
              setUrl(e.target.value);
              setSaveError(null);
            }}
          />
          <button
            disabled={saving || loading || !dirty}
            onClick={() => persist(url.trim() || null)}
          >
            {saving ? "…" : "Save"}
          </button>
        </div>

        {saveError ? <div className="error-banner">{saveError}</div> : null}

        <div className="notif-actions">
          <button
            className="secondary"
            disabled={!saved || dirty || testing}
            onClick={runTest}
            title={
              dirty ? "Save your changes before sending a test." : undefined
            }
          >
            {testing ? "Sending…" : "Send test"}
          </button>
          {saved ? (
            <button
              className="danger"
              disabled={saving}
              onClick={() => {
                setUrl("");
                persist(null);
              }}
            >
              Remove
            </button>
          ) : null}
        </div>

        {dirty && saved ? (
          <p className="muted notif-hint">Save your changes before testing.</p>
        ) : null}
        {test ? (
          <p className={test.ok ? "notif-ok" : "notif-fail"}>
            {test.ok ? "✓ " : "✗ "}
            {test.detail}
          </p>
        ) : null}
      </div>
    </div>
  );
}
