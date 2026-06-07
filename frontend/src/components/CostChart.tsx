import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface CostPoint {
  time: string;
  cost: number; // USD spent in this bucket
}

const TOOLTIP_STYLE = { background: "#0f1626", border: "1px solid #27324a" };

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
          margin={{ top: 8, right: 16, bottom: 0, left: 4 }}
        >
          <defs>
            <linearGradient id="costFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#5b8cff" stopOpacity={0.5} />
              <stop offset="100%" stopColor="#5b8cff" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#27324a" />
          <XAxis
            dataKey="time"
            stroke="#7c8aa5"
            fontSize={12}
            minTickGap={32}
          />
          <YAxis
            stroke="#7c8aa5"
            fontSize={12}
            width={64}
            tickFormatter={usd}
            domain={[0, "auto"]}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={(v: number) => [usd(v), "cost"]}
          />
          <Area
            type="monotone"
            dataKey="cost"
            name="cost"
            stroke="#5b8cff"
            fill="url(#costFill)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
