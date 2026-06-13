import { useState } from "react";

import { createApiKey } from "../api/apikeys";
import { BASE_URL } from "../api/client";
import type { ApiKeyCreated } from "../types";

// Shown on a brand-new account (no workloads yet): a "connect your app" guide.
// Loupe observes calls your app makes via the SDK — there's no account to link —
// so onboarding is: make an ingestion key here, then drop two lines into your
// app pointing at this backend. The snippet is pre-filled with the live API URL
// and (once created) the real key, so it's genuine copy-paste.

function CopyButton({
  text,
  label = "Copy",
}: {
  text: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="secondary copy-btn"
      onClick={() => {
        navigator.clipboard?.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
    >
      {copied ? "Copied" : label}
    </button>
  );
}

function CodeBlock({ code }: { code: string }) {
  return (
    <div className="code-block">
      <pre>
        <code>{code}</code>
      </pre>
      <CopyButton text={code} />
    </div>
  );
}

export default function OnboardingPanel({
  onError,
}: {
  onError: (e: unknown) => void;
}) {
  const [name, setName] = useState("my-app");
  const [creating, setCreating] = useState(false);
  const [fresh, setFresh] = useState<ApiKeyCreated | null>(null);

  async function create() {
    if (!name.trim() || creating) return;
    setCreating(true);
    try {
      setFresh(await createApiKey(name.trim()));
    } catch (e) {
      onError(e);
    } finally {
      setCreating(false);
    }
  }

  const keyValue = fresh?.key ?? "<paste the key from step 1>";
  const workload = name.trim() || "my-app";

  const installSnippet = [
    "pip install loupe-llm",
    "",
    `export LOUPE_URL=${BASE_URL}`,
    `export LOUPE_API_KEY=${keyValue}`,
  ].join("\n");

  const wrapSnippet = [
    "from loupe import track",
    "",
    `client = track(anthropic.Anthropic(), workload="${workload}")`,
    "# use `client` exactly as before — every call is now tracked",
  ].join("\n");

  return (
    <div className="onboarding">
      <div className="onboarding-head">
        <h2>Connect your first app</h2>
        <p className="muted">
          Loupe watches the LLM (or HTTP) calls your app makes — latency,
          tokens, cost, and errors. There's nothing to link: you drop a two-line
          SDK into your app and the data flows here. This page updates live the
          moment your first call lands.
        </p>
      </div>

      <ol className="onboarding-steps">
        <li>
          <div className="step-title">
            <span className="step-num">1</span>
            Create an ingestion key
          </div>
          <p className="muted step-desc">
            Authenticates your app when it ships data to Loupe. Shown once —
            copy it now.
          </p>
          {fresh ? (
            <div className="key-reveal">
              <div className="key-reveal-label">
                Your key <strong>{fresh.name}</strong> — copy it, it won't be
                shown again:
              </div>
              <div className="key-reveal-row">
                <code className="key-value">{fresh.key}</code>
                <CopyButton text={fresh.key} />
              </div>
            </div>
          ) : (
            <div className="key-create">
              <input
                type="text"
                aria-label="app name"
                placeholder="App name (e.g. support-bot)"
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && create()}
              />
              <button disabled={!name.trim() || creating} onClick={create}>
                {creating ? "…" : "Create key"}
              </button>
            </div>
          )}
        </li>

        <li>
          <div className="step-title">
            <span className="step-num">2</span>
            Install the SDK &amp; point it at Loupe
          </div>
          <CodeBlock code={installSnippet} />
        </li>

        <li>
          <div className="step-title">
            <span className="step-num">3</span>
            Wrap your client — two lines
          </div>
          <p className="muted step-desc">
            Works the same for OpenAI:{" "}
            <code>track(OpenAI(), workload="…")</code>.
          </p>
          <CodeBlock code={wrapSnippet} />
        </li>
      </ol>

      <p className="muted onboarding-foot">
        Waiting for your first call… the charts and alerts above fill in
        automatically.
      </p>
    </div>
  );
}
