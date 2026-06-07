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

export interface TokenPoint {
  time: string;
  input: number; // input (prompt) tokens in this bucket
  output: number; // output (completion) tokens in this bucket
}

const TOOLTIP_STYLE = { background: "#0f1626", border: "1px solid #27324a" };

export default function TokenChart({ data }: { data: TokenPoint[] }) {
  return (
    <div className="panel">
      <h3>Token throughput (input / output)</h3>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart
          data={data}
          margin={{ top: 8, right: 16, bottom: 0, left: 4 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#27324a" />
          <XAxis
            dataKey="time"
            stroke="#7c8aa5"
            fontSize={12}
            minTickGap={32}
          />
          <YAxis stroke="#7c8aa5" fontSize={12} width={56} />
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Legend />
          <Area
            type="monotone"
            dataKey="input"
            name="input"
            stackId="tokens"
            stroke="#22d3ee"
            fill="#22d3ee"
            fillOpacity={0.25}
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="output"
            name="output"
            stackId="tokens"
            stroke="#a78bfa"
            fill="#a78bfa"
            fillOpacity={0.25}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
