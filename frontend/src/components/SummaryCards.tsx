import type { MetricsSummary } from "../types";

function Card({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="card">
      <div className="card-label">{label}</div>
      <div className="card-value">{value}</div>
      {sub ? <div className="card-sub">{sub}</div> : null}
    </div>
  );
}

function ms(value: number | null): string {
  return value == null ? "—" : `${Math.round(value)}ms`;
}

export default function SummaryCards({
  summary,
}: {
  summary: MetricsSummary | null;
}) {
  return (
    <div className="cards">
      <Card
        label="Requests"
        value={summary ? String(summary.request_count) : "—"}
        sub={summary ? `last ${summary.window}` : ""}
      />
      <Card
        label="Error rate"
        value={summary ? `${(summary.error_rate * 100).toFixed(1)}%` : "—"}
        sub={summary ? `${summary.error_count} errors` : ""}
      />
      <Card label="Latency p50" value={ms(summary?.latency_p50_ms ?? null)} />
      <Card label="Latency p95" value={ms(summary?.latency_p95_ms ?? null)} />
    </div>
  );
}
