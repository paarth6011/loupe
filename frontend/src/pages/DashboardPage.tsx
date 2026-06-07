import { useCallback, useEffect, useState } from "react";

import { listAlerts } from "../api/alerts";
import { ApiError } from "../api/client";
import { getCost, getSummary, getTimeseries } from "../api/metrics";
import { listWorkloads } from "../api/workloads";
import AlertsPanel from "../components/AlertsPanel";
import ApiKeysPanel from "../components/ApiKeysPanel";
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
const POLL_MS = 3000;

function formatBucket(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
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

    tick(selectedId);
    const id = setInterval(() => tick(selectedId), POLL_MS);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [selectedId, timeWindow]);

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
        <div className="brand">🔎 Loupe</div>
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
        <button
          className="secondary"
          disabled={selectedId == null}
          onClick={() => setShowMonitors(true)}
        >
          ⚙ Monitors
        </button>
        <button className="secondary" onClick={() => setShowKeys(true)}>
          🔑 API keys
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
          <AlertsPanel alerts={alerts} workloads={workloads} />
        </aside>
      </main>

      <footer className="foot">
        {selected ? `Monitoring "${selected.name}"` : "No workloads yet"} ·
        polling every {POLL_MS / 1000}s
      </footer>
    </div>
  );
}
