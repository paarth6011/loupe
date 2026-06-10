import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AXIS_PROPS, CHART, ChartTooltip, glow } from "./chartTheme";

export interface ErrorPoint {
  time: string;
  errorRate: number; // percentage 0–100
}

const fmtPct = (v: number) => `${v.toFixed(2)}%`;

export default function ErrorRateChart({ data }: { data: ErrorPoint[] }) {
  return (
    <div className="panel">
      <h3>Error rate over time</h3>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart
          data={data}
          margin={{ top: 8, right: 12, bottom: 0, left: -8 }}
        >
          <defs>
            <linearGradient id="errFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={CHART.error} stopOpacity={0.45} />
              <stop offset="100%" stopColor={CHART.error} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="2 4" vertical={false} />
          <XAxis dataKey="time" {...AXIS_PROPS} minTickGap={36} />
          <YAxis
            {...AXIS_PROPS}
            width={40}
            domain={[0, "auto"]}
            tickFormatter={(v) => `${v}%`}
          />
          <Tooltip
            cursor={{ stroke: "#3a4456" }}
            content={<ChartTooltip format={fmtPct} />}
          />
          <Area
            type="monotone"
            dataKey="errorRate"
            name="error rate"
            stroke={CHART.error}
            strokeWidth={2}
            fill="url(#errFill)"
            activeDot={{ r: 3, strokeWidth: 0 }}
            style={glow(CHART.error)}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
