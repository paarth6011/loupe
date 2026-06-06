export interface Workload {
  id: number;
  name: string;
  created_at: string;
}

export interface Alert {
  id: number;
  workload_id: number;
  rule: string;
  message: string;
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
}

export interface TimeseriesPoint {
  bucket_start: string;
  request_count: number;
  error_rate: number;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
}

export interface MetricsTimeseries {
  workload_id: number;
  window: string;
  bucket: string;
  points: TimeseriesPoint[];
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}
