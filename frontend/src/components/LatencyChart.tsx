import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AXIS_PROPS, CHART, ChartTooltip, glow } from "./chartTheme";

export interface LatencyPoint {
  time: string;
  p50: number | null;
  p95: number | null;
}

const fmtMs = (v: number) => `${Math.round(v)}ms`;

export default function LatencyChart({ data }: { data: LatencyPoint[] }) {
  return (
    <div className="panel">
      <h3>Latency over time (p50 / p95)</h3>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart
          data={data}
          margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
        >
          <CartesianGrid strokeDasharray="2 4" vertical={false} />
          <XAxis dataKey="time" {...AXIS_PROPS} minTickGap={36} />
          <YAxis {...AXIS_PROPS} width={58} tickFormatter={fmtMs} />
          <Tooltip
            cursor={{ stroke: "#3a4456" }}
            content={<ChartTooltip format={fmtMs} />}
          />
          <Legend iconType="plainline" />
          <Line
            type="monotone"
            dataKey="p50"
            name="p50"
            stroke={CHART.p50}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 3, strokeWidth: 0 }}
            style={glow(CHART.p50)}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="p95"
            name="p95"
            stroke={CHART.p95}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 3, strokeWidth: 0 }}
            style={glow(CHART.p95)}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
