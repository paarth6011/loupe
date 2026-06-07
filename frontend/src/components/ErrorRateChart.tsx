import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface ErrorPoint {
  time: string;
  errorRate: number; // percentage 0–100
}

const TOOLTIP_STYLE = { background: "#0f1626", border: "1px solid #27324a" };

export default function ErrorRateChart({ data }: { data: ErrorPoint[] }) {
  return (
    <div className="panel">
      <h3>Error rate over time</h3>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart
          data={data}
          margin={{ top: 8, right: 16, bottom: 0, left: -8 }}
        >
          <defs>
            <linearGradient id="errFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f87171" stopOpacity={0.5} />
              <stop offset="100%" stopColor="#f87171" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#27324a" />
          <XAxis
            dataKey="time"
            stroke="#7c8aa5"
            fontSize={12}
            minTickGap={32}
          />
          <YAxis stroke="#7c8aa5" fontSize={12} unit="%" domain={[0, "auto"]} />
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Area
            type="monotone"
            dataKey="errorRate"
            name="error rate"
            stroke="#f87171"
            fill="url(#errFill)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
