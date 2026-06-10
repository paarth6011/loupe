import { useCallback, useEffect, useState } from "react";

import { listAlerts, reopenAlert, resolveAlert } from "../api/alerts";
import { ApiError } from "../api/client";
import { openEventStream } from "../api/events";
import { getCost, getSummary, getTimeseries } from "../api/metrics";
import { setWorkloadPublic } from "../api/status";
import { listWorkloads } from "../api/workloads";
import AlertsPanel from "../components/AlertsPanel";
import ApiKeysPanel from "../components/ApiKeysPanel";
import Brand from "../components/Brand";
import CostBreakdown from "../components/CostBreakdown";
import CostChart, { type CostPoint } from "../components/CostChart";
import ErrorRateChart, { type ErrorPoint } from "../components/ErrorRateChart";
import LatencyChart, { type LatencyPoint } from "../components/LatencyChart";
import MonitorsPanel from "../components/MonitorsPanel";
import SummaryCards from "../components/SummaryCards";
import TokenChart, { type TokenPoint } from "../components/TokenChart";
import type { Alert, CostSummary, MetricsSummary, Workload } from "../types";

const WINDOWS = ["5m", "15m", "1h", "6h", "24h", "7d"];
// Bucket granularity per window — keeps each chart around 12–48 points.
const BUCKET_FOR: Record<string, string> = {
  "5m": "15s",
  "15m": "1m",
  "1h": "5m",
  "6h": "15m",
  "24h": "30m",
  "7d": "6h",
};
// Live updates arrive over SSE; this slow interval is only a safety net in case
// the stream stalls (e.g. a flaky proxy that swallows the connection silently).
const FALLBACK_MS = 30000;

function formatBucket(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

// Small inline stroke icon for topbar actions (SVG, not emoji).
function Icon({ path }: { path: string }) {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={path} />
    </svg>
  );
}

export default function DashboardPage({ onLogout }: { onLogout: () => void }) {
  const [workloads, setWorkloads] = useState<Workload[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [timeWindow, setTimeWindow] = useState("1h");
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [latency, setLatency] = useState<LatencyPoint[]>([]);
  const [errors, setErrors] = useState<ErrorPoint[]>([]);
  const [tokens, setTokens] = useState<TokenPoint[]>([]);
  const [costSeries, setCostSeries] = useState<CostPoint[]>([]);
  const [cost, setCost] = useState<CostSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showMonitors, setShowMonitors] = useState(false);
  const [showKeys, setShowKeys] = useState(false);
  // Manual alert resolve: which alert is mid-request (to disable its button),
  // and the most recently resolved alert offering a brief Undo.
  const [resolvingId, setResolvingId] = useState<number | null>(null);
  const [undo, setUndo] = useState<{ id: number; rule: string } | null>(null);

  // Stable across renders so it can sit in child effect deps without causing
  // a refetch on every poll (which would otherwise wipe in-progress edits).
  const handleError = useCallback(
    (e: unknown) => {
      if (e instanceof ApiError && e.status === 401) {
        onLogout();
        return;
      }
      setError(e instanceof Error ? e.message : "Request failed");
    },
    [onLogout],
  );

  // Publish/unpublish the selected workload on the public status page.
  async function togglePublic(next: boolean) {
    if (selectedId == null) return;
    try {
      const updated = await setWorkloadPublic(selectedId, next);
      setWorkloads((ws) => ws.map((w) => (w.id === updated.id ? updated : w)));
    } catch (e) {
      handleError(e);
    }
  }

  // Resolve an alert. Update the list optimistically (the fallback poll is 30s
  // away, so we don't want to wait for it), then persist. On failure, roll the
  // alert back to open and surface the error. On success, offer a brief Undo.
  const handleResolve = useCallback(
    async (alert: Alert) => {
      const stamp = new Date().toISOString();
      setResolvingId(alert.id);
      setAlerts((as) =>
        as.map((a) => (a.id === alert.id ? { ...a, resolved_at: stamp } : a)),
      );
      try {
        const updated = await resolveAlert(alert.id);
        setAlerts((as) => as.map((a) => (a.id === updated.id ? updated : a)));
        setUndo({ id: alert.id, rule: alert.rule });
      } catch (e) {
        setAlerts((as) =>
          as.map((a) => (a.id === alert.id ? { ...a, resolved_at: null } : a)),
        );
        handleError(e);
      } finally {
        setResolvingId(null);
      }
    },
    [handleError],
  );

  // Undo a manual resolve by reopening the alert (optimistic, same as above).
  const handleUndo = useCallback(async () => {
    if (undo == null) return;
    const id = undo.id;
    setUndo(null);
    setResolvingId(id);
    setAlerts((as) =>
      as.map((a) => (a.id === id ? { ...a, resolved_at: null } : a)),
    );
    try {
      const updated = await reopenAlert(id);
      setAlerts((as) => as.map((a) => (a.id === updated.id ? updated : a)));
    } catch (e) {
      handleError(e);
    } finally {
      setResolvingId(null);
    }
  }, [undo, handleError]);

  // Auto-dismiss the Undo affordance after a short window (the resolve is
  // already persisted; this just retires the second-chance prompt).
  useEffect(() => {
    if (undo == null) return;
    const t = setTimeout(() => setUndo(null), 6000);
    return () => clearTimeout(t);
  }, [undo]);

  // Load workloads once and default the selection to the first one.
  useEffect(() => {
    listWorkloads()
      .then((wls) => {
        setWorkloads(wls);
        setSelectedId((cur) => cur ?? wls[0]?.id ?? null);
      })
      .catch(handleError);
  }, []);

  // Reset the live series whenever the workload or window changes.
  useEffect(() => {
    setLatency([]);
    setErrors([]);
    setTokens([]);
    setCostSeries([]);
  }, [selectedId, timeWindow]);

  // Poll summary + alerts, accumulating a client-side time-series.
  useEffect(() => {
    if (selectedId == null) return;
    let active = true;

    async function tick(workloadId: number) {
      const bucket = BUCKET_FOR[timeWindow] ?? "5m";
      try {
        const [s, ts, c, a, wls] = await Promise.all([
          getSummary(workloadId, timeWindow),
          getTimeseries(workloadId, timeWindow, bucket),
          getCost(timeWindow),
          listAlerts(),
          listWorkloads(),
        ]);
        if (!active) return;
        setSummary(s);
        setCost(c);
        setAlerts(a);
        setWorkloads(wls);
        setError(null);
        // Charts come straight from the bucketed history endpoint, so they're
        // fully populated on load and survive a refresh.
        setLatency(
          ts.points.map((p) => ({
            time: formatBucket(p.bucket_start),
            p50: p.latency_p50_ms,
            p95: p.latency_p95_ms,
          })),
        );
        setErrors(
          ts.points.map((p) => ({
            time: formatBucket(p.bucket_start),
            errorRate: +(p.error_rate * 100).toFixed(2),
          })),
        );
        setTokens(
          ts.points.map((p) => ({
            time: formatBucket(p.bucket_start),
            input: p.input_tokens,
            output: p.output_tokens,
          })),
        );
        setCostSeries(
          ts.points.map((p) => ({
            time: formatBucket(p.bucket_start),
            cost: p.cost_usd,
          })),
        );
      } catch (e) {
        if (active) handleError(e);
      }
    }

    // Initial load, then refetch whenever the server says data changed. A slow
    // fallback interval covers the rare case where the stream stalls silently.
    tick(selectedId);
    const stop = openEventStream(() => {
      if (active) tick(selectedId);
    }, onLogout);
    const fallback = setInterval(() => tick(selectedId), FALLBACK_MS);
    return () => {
      active = false;
      stop();
      clearInterval(fallback);
    };
  }, [selectedId, timeWindow, onLogout]);

  const selected = workloads.find((w) => w.id === selectedId) ?? null;
  // Only show token/cost charts for workloads that actually report LLM usage,
  // so HTTP-only workloads keep the lean latency/error view.
  const isLlm =
    summary != null &&
    (summary.total_cost_usd > 0 ||
      summary.total_input_tokens > 0 ||
      summary.total_output_tokens > 0);

  return (
    <div className="app">
      <header className="topbar">
        <Brand />
        <div className="spacer" />
        <select
          aria-label="workload"
          value={selectedId ?? ""}
          onChange={(e) => setSelectedId(Number(e.target.value))}
        >
          {workloads.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
        <select
          aria-label="window"
          value={timeWindow}
          onChange={(e) => setTimeWindow(e.target.value)}
        >
          {WINDOWS.map((w) => (
            <option key={w} value={w}>
              {w}
            </option>
          ))}
        </select>
        <label className="public-toggle" title="Show on the public status page">
          <input
            type="checkbox"
            checked={selected?.public ?? false}
            disabled={selectedId == null}
            onChange={(e) => togglePublic(e.target.checked)}
          />
          Public
        </label>
        <a
          className="secondary linkbtn"
          href="/status"
          target="_blank"
          rel="noreferrer"
        >
          <Icon path="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20ZM2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20" />
          Status page
        </a>
        <button
          className="secondary"
          disabled={selectedId == null}
          onClick={() => setShowMonitors(true)}
        >
          <Icon path="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8" />
          Monitors
        </button>
        <button className="secondary" onClick={() => setShowKeys(true)}>
          <Icon path="M2 18v3h3l8.5-8.5M21 7.5a4.5 4.5 0 1 1-9 0 4.5 4.5 0 0 1 9 0Z" />
          API keys
        </button>
        <button onClick={onLogout}>Log out</button>
      </header>

      {showMonitors && selected ? (
        <MonitorsPanel
          workloadId={selected.id}
          workloadName={selected.name}
          onClose={() => setShowMonitors(false)}
          onError={handleError}
        />
      ) : null}

      {showKeys ? (
        <ApiKeysPanel
          onClose={() => setShowKeys(false)}
          onError={handleError}
        />
      ) : null}

      {error ? <div className="error-banner">{error}</div> : null}

      <main className="content">
        <section className="main-col">
          <SummaryCards summary={summary} />
          <LatencyChart data={latency} />
          <ErrorRateChart data={errors} />
          {isLlm ? (
            <>
              <CostChart data={costSeries} />
              <TokenChart data={tokens} />
            </>
          ) : null}
          <CostBreakdown cost={cost} />
        </section>
        <aside className="side-col">
          <AlertsPanel
            alerts={alerts}
            workloads={workloads}
            onResolve={handleResolve}
            resolvingId={resolvingId}
          />
        </aside>
      </main>

      <footer className="foot">
        {selected ? `Monitoring "${selected.name}"` : "No workloads yet"} · live
        updates (SSE)
      </footer>

      {undo ? (
        <div className="toast" role="status" aria-live="polite">
          <span className="toast-msg">
            Resolved <strong>{undo.rule}</strong>
          </span>
          <button className="toast-undo" onClick={handleUndo}>
            Undo
          </button>
        </div>
      ) : null}
    </div>
  );
}
