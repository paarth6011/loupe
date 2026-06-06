import { useEffect, useState } from "react";

import { listAlerts } from "../api/alerts";
import { ApiError } from "../api/client";
import { getSummary } from "../api/metrics";
import { listWorkloads } from "../api/workloads";
import AlertsPanel from "../components/AlertsPanel";
import ErrorRateChart, { type ErrorPoint } from "../components/ErrorRateChart";
import LatencyChart, { type LatencyPoint } from "../components/LatencyChart";
import SummaryCards from "../components/SummaryCards";
import type { Alert, MetricsSummary, Workload } from "../types";

const WINDOWS = ["15m", "1h", "24h"];
const POLL_MS = 3000;
const MAX_POINTS = 40;

export default function DashboardPage({ onLogout }: { onLogout: () => void }) {
  const [workloads, setWorkloads] = useState<Workload[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [timeWindow, setTimeWindow] = useState("1h");
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [latency, setLatency] = useState<LatencyPoint[]>([]);
  const [errors, setErrors] = useState<ErrorPoint[]>([]);
  const [error, setError] = useState<string | null>(null);

  function handleError(e: unknown) {
    if (e instanceof ApiError && e.status === 401) {
      onLogout();
      return;
    }
    setError(e instanceof Error ? e.message : "Request failed");
  }

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
  }, [selectedId, timeWindow]);

  // Poll summary + alerts, accumulating a client-side time-series.
  useEffect(() => {
    if (selectedId == null) return;
    let active = true;

    async function tick(workloadId: number) {
      try {
        const [s, a, wls] = await Promise.all([
          getSummary(workloadId, timeWindow),
          listAlerts(),
          listWorkloads(),
        ]);
        if (!active) return;
        setSummary(s);
        setAlerts(a);
        setWorkloads(wls);
        setError(null);
        const t = new Date().toLocaleTimeString();
        setLatency((prev) =>
          [...prev, { time: t, p50: s.latency_p50_ms, p95: s.latency_p95_ms }].slice(
            -MAX_POINTS,
          ),
        );
        setErrors((prev) =>
          [...prev, { time: t, errorRate: +(s.error_rate * 100).toFixed(2) }].slice(
            -MAX_POINTS,
          ),
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

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">☁️ Cloud Ops Dashboard</div>
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
        <button onClick={onLogout}>Log out</button>
      </header>

      {error ? <div className="error-banner">{error}</div> : null}

      <main className="content">
        <section className="main-col">
          <SummaryCards summary={summary} />
          <LatencyChart data={latency} />
          <ErrorRateChart data={errors} />
        </section>
        <aside className="side-col">
          <AlertsPanel alerts={alerts} workloads={workloads} />
        </aside>
      </main>

      <footer className="foot">
        {selected ? `Monitoring "${selected.name}"` : "No workloads yet"} · polling
        every {POLL_MS / 1000}s
      </footer>
    </div>
  );
}
