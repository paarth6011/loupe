import { useEffect, useState } from "react";

import { getStatus } from "../api/status";
import Brand from "../components/Brand";
import type { StatusComponent, StatusPage as StatusPageData } from "../types";

const REFRESH_MS = 15000;

const STATUS_LABEL: Record<StatusComponent["status"], string> = {
  operational: "Operational",
  degraded: "Degraded",
  down: "Outage",
  unknown: "No recent data",
};

const OVERALL_HEADLINE: Record<StatusPageData["overall"], string> = {
  operational: "All systems operational",
  degraded: "Partial degradation",
  down: "Major outage",
};

function relativeTime(iso: string | null): string {
  if (!iso) return "never";
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

export default function StatusPage() {
  const [data, setData] = useState<StatusPageData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const d = await getStatus();
        if (active) {
          setData(d);
          setError(null);
        }
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : "Request failed");
      }
    }
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="status-page">
      <header className="status-head">
        <Brand />
        <div className="status-subtitle">Service status</div>
      </header>

      {error ? <div className="error-banner">{error}</div> : null}

      {data ? (
        <>
          <div className={`status-overall status-${data.overall}`}>
            <span className="status-dot" />
            {OVERALL_HEADLINE[data.overall]}
          </div>

          {data.components.length === 0 ? (
            <p className="status-empty">No services are currently published.</p>
          ) : (
            <ul className="status-list">
              {data.components.map((c) => (
                <li key={c.name} className="status-row">
                  <span className="status-name">{c.name}</span>
                  <span className="status-meta">
                    {c.uptime_24h != null
                      ? `${c.uptime_24h.toFixed(2)}% · 24h`
                      : "—"}
                    {c.latency_p50_ms != null
                      ? ` · ${Math.round(c.latency_p50_ms)}ms p50`
                      : ""}
                    {` · checked ${relativeTime(c.last_sample_at)}`}
                  </span>
                  <span className={`status-badge status-${c.status}`}>
                    <span className="status-dot" />
                    {STATUS_LABEL[c.status]}
                  </span>
                </li>
              ))}
            </ul>
          )}

          <footer className="status-foot">
            Updated {relativeTime(data.generated_at)} · refreshes every{" "}
            {REFRESH_MS / 1000}s
          </footer>
        </>
      ) : !error ? (
        <p className="status-empty">Loading…</p>
      ) : null}
    </div>
  );
}
