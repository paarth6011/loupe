import type { CostSummary } from "../types";

function usd(value: number): string {
  if (value === 0) return "$0";
  if (value < 0.01) return `$${value.toFixed(5)}`;
  return `$${value.toFixed(2)}`;
}

function compact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export default function CostBreakdown({ cost }: { cost: CostSummary | null }) {
  const hasSpend = cost != null && cost.total_cost_usd > 0;

  return (
    <div className="panel">
      <div className="breakdown-head">
        <h3>Spend breakdown</h3>
        <span className="muted">account-wide · last {cost?.window ?? "—"}</span>
      </div>

      {!hasSpend ? (
        <p className="muted breakdown-empty">
          No LLM spend recorded in this window. Instrument an app with the{" "}
          <code>loupe</code> SDK to see cost by model and workload here.
        </p>
      ) : (
        <>
          <div className="breakdown-totals">
            <div>
              <div className="card-label">Total cost</div>
              <div className="breakdown-total-value">
                {usd(cost.total_cost_usd)}
              </div>
            </div>
            <div>
              <div className="card-label">Tokens (in / out)</div>
              <div className="breakdown-total-value">
                {compact(cost.total_input_tokens)} /{" "}
                {compact(cost.total_output_tokens)}
              </div>
            </div>
            <div>
              <div className="card-label">Requests</div>
              <div className="breakdown-total-value">
                {compact(cost.total_requests)}
              </div>
            </div>
          </div>

          <div className="breakdown-section-title">By model</div>
          <table className="breakdown-table">
            <thead>
              <tr>
                <th>Model</th>
                <th>Reqs</th>
                <th>In</th>
                <th>Out</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              {cost.by_model.map((m) => (
                <tr key={`${m.provider ?? ""}:${m.model}`}>
                  <td>
                    {m.model}
                    {m.provider ? (
                      <span className="muted"> · {m.provider}</span>
                    ) : null}
                  </td>
                  <td>{compact(m.requests)}</td>
                  <td>{compact(m.input_tokens)}</td>
                  <td>{compact(m.output_tokens)}</td>
                  <td>{usd(m.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="breakdown-section-title">By workload</div>
          <table className="breakdown-table">
            <thead>
              <tr>
                <th>Workload</th>
                <th>Reqs</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              {cost.by_workload.map((w) => (
                <tr key={w.workload_id}>
                  <td>{w.workload}</td>
                  <td>{compact(w.requests)}</td>
                  <td>{usd(w.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
