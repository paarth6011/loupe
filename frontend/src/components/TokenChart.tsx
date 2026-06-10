import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AXIS_PROPS, CHART, ChartTooltip } from "./chartTheme";

export interface TokenPoint {
  time: string;
  input: number; // input (prompt) tokens in this bucket
  output: number; // output (completion) tokens in this bucket
}

function compact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(Math.round(n));
}

export default function TokenChart({ data }: { data: TokenPoint[] }) {
  return (
    <div className="panel">
      <h3>Token throughput (input / output)</h3>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart
          data={data}
          margin={{ top: 8, right: 12, bottom: 0, left: 4 }}
        >
          <defs>
            <linearGradient id="tokInFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={CHART.tokenIn} stopOpacity={0.4} />
              <stop
                offset="100%"
                stopColor={CHART.tokenIn}
                stopOpacity={0.02}
              />
            </linearGradient>
            <linearGradient id="tokOutFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={CHART.tokenOut} stopOpacity={0.4} />
              <stop
                offset="100%"
                stopColor={CHART.tokenOut}
                stopOpacity={0.02}
              />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="2 4" vertical={false} />
          <XAxis dataKey="time" {...AXIS_PROPS} minTickGap={36} />
          <YAxis {...AXIS_PROPS} width={48} tickFormatter={compact} />
          <Tooltip
            cursor={{ stroke: "#3a4456" }}
            content={<ChartTooltip format={compact} />}
          />
          <Legend iconType="plainline" />
          <Area
            type="monotone"
            dataKey="input"
            name="input"
            stackId="tokens"
            stroke={CHART.tokenIn}
            strokeWidth={2}
            fill="url(#tokInFill)"
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="output"
            name="output"
            stackId="tokens"
            stroke={CHART.tokenOut}
            strokeWidth={2}
            fill="url(#tokOutFill)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
