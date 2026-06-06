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

export interface LatencyPoint {
  time: string;
  p50: number | null;
  p95: number | null;
}

const TOOLTIP_STYLE = { background: "#0f1626", border: "1px solid #27324a" };

export default function LatencyChart({ data }: { data: LatencyPoint[] }) {
  return (
    <div className="panel">
      <h3>Latency over time (p50 / p95)</h3>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#27324a" />
          <XAxis dataKey="time" stroke="#7c8aa5" fontSize={12} minTickGap={32} />
          <YAxis stroke="#7c8aa5" fontSize={12} unit="ms" />
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Legend />
          <Line
            type="monotone"
            dataKey="p50"
            name="p50"
            stroke="#4ade80"
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="p95"
            name="p95"
            stroke="#f59e0b"
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
