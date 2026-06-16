import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AXIS_PROPS, CHART, glow } from "./chartTheme";
import type { BaselineProfile } from "../types";

// The learned seasonal baseline for a workload, drawn as its typical latency
// across the 24 hours of the day. Each point is the robust median the anomaly
// detector compares against for that hour; gaps are hours not yet learned. The
// coverage badge ("active · N/24h") is the visible signal that the seasonal
// path is actually working — vs silently falling back to the rolling window.

const HOURS = 24;
const fmtMs = (v: number) => `${Math.round(v)}ms`;

interface HourPoint {
  hour: string;
  typical: number | null;
  scale: number | null;
  n: number | null;
}

function buildPoints(latency: BaselineProfile[]): HourPoint[] {
  const byBucket = new Map(latency.map((b) => [b.bucket, b]));
  return Array.from({ length: HOURS }, (_, h) => {
    const b = byBucket.get(h);
    return {
      hour: `${String(h).padStart(2, "0")}:00`,
      typical: b ? Math.round(b.center) : null,
      scale: b ? b.scale : null,
      n: b ? b.n : null,
    };
  });
}

function BaselineTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { payload: HourPoint }[];
  label?: string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const p = payload[0].payload;
  if (p.typical == null) return null;
  return (
    <div className="chart-tip">
      <div className="chart-tip-label">{label} UTC</div>
      <div className="chart-tip-row">
        <span className="chart-tip-dot" style={{ background: CHART.p50 }} />
        <span className="chart-tip-name">typical</span>
        <span className="chart-tip-val">
          {fmtMs(p.typical)} ± {fmtMs(p.scale ?? 0)}
        </span>
      </div>
      <div className="chart-tip-row">
        <span className="chart-tip-name">samples</span>
        <span className="chart-tip-val">{p.n}</span>
      </div>
    </div>
  );
}

export default function SeasonalBaselinePanel({
  baselines,
}: {
  baselines: BaselineProfile[];
}) {
  const latency = baselines.filter((b) => b.metric === "latency");
  const learned = latency.length;
  const points = buildPoints(latency);

  return (
    <div className="panel">
      <div className="baseline-head">
        <h3>Typical latency by hour</h3>
        <span
          className={`baseline-badge ${learned ? "is-active" : "is-learning"}`}
        >
          {learned
            ? `seasonal detection active · ${learned}/24h`
            : "learning · needs ~3 weeks of history"}
        </span>
      </div>
      {learned ? (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart
            data={points}
            margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
          >
            <CartesianGrid strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="hour"
              {...AXIS_PROPS}
              interval={2}
              minTickGap={16}
            />
            <YAxis {...AXIS_PROPS} width={58} tickFormatter={fmtMs} />
            <Tooltip
              cursor={{ stroke: "#3a4456" }}
              content={<BaselineTooltip />}
            />
            <Line
              type="monotone"
              dataKey="typical"
              name="typical"
              stroke={CHART.p50}
              strokeWidth={2}
              dot={{ r: 2, strokeWidth: 0, fill: CHART.p50 }}
              activeDot={{ r: 4, strokeWidth: 0 }}
              style={glow(CHART.p50)}
              connectNulls={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <p className="baseline-empty">
          Loupe is learning this workload's normal latency for each hour of the
          day. Once an hour has enough history, anomaly alerts compare against
          its own typical value instead of a flat baseline — so a predictably
          busy hour won't false-positive. Until then the rolling-window detector
          is used.
        </p>
      )}
    </div>
  );
}
