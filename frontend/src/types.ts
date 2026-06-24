export interface Workload {
  id: number;
  name: string;
  created_at: string;
  public: boolean;
}

export interface BaselineProfile {
  metric: string; // "latency" | "cost"
  bucket: number; // UTC hour-of-day, 0–23
  center: number; // learned median
  scale: number; // robust spread (MAD×1.4826)
  n: number; // samples behind this bucket
}

export interface StatusComponent {
  name: string;
  status: "operational" | "degraded" | "down" | "unknown";
  uptime_24h: number | null;
  latency_p50_ms: number | null;
  last_sample_at: string | null;
}

export interface StatusPage {
  overall: "operational" | "degraded" | "down";
  generated_at: string;
  components: StatusComponent[];
}

export interface Alert {
  id: number;
  workload_id: number;
  rule: string;
  message: string;
  severity: string;
  detector: string;
  summary: string | null;
  triggered_at: string;
  resolved_at: string | null;
}

export interface MetricsSummary {
  workload_id: number;
  window: string;
  request_count: number;
  error_count: number;
  error_rate: number;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
}

export interface TimeseriesPoint {
  bucket_start: string;
  request_count: number;
  error_rate: number;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface CostByModel {
  model: string;
  provider: string | null;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface CostByWorkload {
  workload_id: number;
  workload: string;
  requests: number;
  cost_usd: number;
}

export interface CostSummary {
  window: string;
  total_requests: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  by_model: CostByModel[];
  by_workload: CostByWorkload[];
}

export interface MetricsTimeseries {
  workload_id: number;
  window: string;
  bucket: string;
  points: TimeseriesPoint[];
}

export interface Monitor {
  rule: string;
  label: string;
  unit: string;
  detector: string;
  integer: boolean;
  enabled: boolean;
  threshold: number | null;
  default_threshold: number;
  effective_threshold: number;
}

export interface ApiKey {
  id: number;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
}

export interface ApiKeyCreated extends ApiKey {
  key: string; // full plaintext, returned only once at creation
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface NotificationSettings {
  webhook_url: string | null;
}

export interface NotificationTestResult {
  ok: boolean;
  detail: string;
}

// The browser only ever sees whether a Gemini key is set plus a masked hint —
// never the key itself.
export interface SummarizerKeySettings {
  gemini_key_set: boolean;
  gemini_key_hint: string | null;
}
