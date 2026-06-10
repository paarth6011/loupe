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

export interface CostPoint {
  time: string;
  cost: number; // USD spent in this bucket
}

function usd(value: number): string {
  if (value === 0) return "$0";
  if (value < 0.01) return `$${value.toFixed(5)}`;
  return `$${value.toFixed(2)}`;
}

export default function CostChart({ data }: { data: CostPoint[] }) {
  return (
    <div className="panel">
      <h3>Cost over time</h3>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart
          data={data}
          margin={{ top: 8, right: 12, bottom: 0, left: 4 }}
        >
          <defs>
            <linearGradient id="costFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={CHART.cost} stopOpacity={0.45} />
              <stop offset="100%" stopColor={CHART.cost} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="2 4" vertical={false} />
          <XAxis dataKey="time" {...AXIS_PROPS} minTickGap={36} />
          <YAxis
            {...AXIS_PROPS}
            width={60}
            tickFormatter={usd}
            domain={[0, "auto"]}
          />
          <Tooltip
            cursor={{ stroke: "#3a4456" }}
            content={<ChartTooltip format={usd} />}
          />
          <Area
            type="monotone"
            dataKey="cost"
            name="cost"
            stroke={CHART.cost}
            strokeWidth={2}
            fill="url(#costFill)"
            activeDot={{ r: 3, strokeWidth: 0 }}
            style={glow(CHART.cost)}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
