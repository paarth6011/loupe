import type { CSSProperties, ReactNode } from "react";

import type { MetricsSummary } from "../types";

function Card({
  label,
  value,
  sub,
  accent,
  icon,
}: {
  label: string;
  value: string;
  sub?: string;
  accent: string;
  icon: ReactNode;
}) {
  return (
    <div className="card" style={{ "--card-accent": accent } as CSSProperties}>
      <div className="card-top">
        <div className="card-label">{label}</div>
        <div className="card-icon">{icon}</div>
      </div>
      <div className="card-value">{value}</div>
      {sub ? <div className="card-sub">{sub}</div> : null}
    </div>
  );
}

function ms(value: number | null): string {
  return value == null ? "—" : `${Math.round(value)}ms`;
}

// Lucide-style stroke icons (SVG, not emoji — consistent stroke width + theming).
const I = {
  requests: (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  ),
  error: (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </svg>
  ),
  gauge: (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="m12 14 4-4" />
      <path d="M3.34 19a10 10 0 1 1 17.32 0" />
    </svg>
  ),
  timer: (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="10" x2="14" y1="2" y2="2" />
      <line x1="12" x2="15" y1="14" y2="11" />
      <circle cx="12" cy="14" r="8" />
    </svg>
  ),
};

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
        accent="var(--primary)"
        icon={I.requests}
      />
      <Card
        label="Error rate"
        value={summary ? `${(summary.error_rate * 100).toFixed(1)}%` : "—"}
        sub={summary ? `${summary.error_count} errors` : ""}
        accent="var(--red)"
        icon={I.error}
      />
      <Card
        label="Latency p50"
        value={ms(summary?.latency_p50_ms ?? null)}
        accent="var(--green)"
        icon={I.gauge}
      />
      <Card
        label="Latency p95"
        value={ms(summary?.latency_p95_ms ?? null)}
        accent="var(--amber)"
        icon={I.timer}
      />
    </div>
  );
}
