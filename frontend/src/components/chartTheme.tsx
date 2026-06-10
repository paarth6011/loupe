// Shared chart styling so every Recharts panel reads as one system: the same
// palette as the CSS tokens, a glow on series lines, and a custom dark tooltip
// with tabular-figure values.

export const CHART = {
  p50: "#34d399",
  p95: "#fbbf24",
  error: "#fb7185",
  cost: "#5e9bff",
  tokenIn: "#2dd4bf",
  tokenOut: "#a78bfa",
};

export const AXIS_PROPS = {
  stroke: "#3a4456",
  tick: { fill: "#69748a" },
  tickLine: false,
  fontSize: 11,
} as const;

export function glow(color: string) {
  return { filter: `drop-shadow(0 0 5px ${color}66)` };
}

interface TipPayload {
  name: string;
  value: number;
  color?: string;
  stroke?: string;
  fill?: string;
}

export function ChartTooltip({
  active,
  payload,
  label,
  format,
}: {
  active?: boolean;
  payload?: TipPayload[];
  label?: string;
  format?: (v: number) => string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const fmt = format ?? ((v: number) => String(v));
  return (
    <div className="chart-tip">
      <div className="chart-tip-label">{label}</div>
      {payload.map((p, i) => (
        <div className="chart-tip-row" key={i}>
          <span
            className="chart-tip-dot"
            style={{ background: p.color ?? p.stroke ?? p.fill }}
          />
          <span className="chart-tip-name">{p.name}</span>
          <span className="chart-tip-val">{fmt(Number(p.value))}</span>
        </div>
      ))}
    </div>
  );
}
