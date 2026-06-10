import type { Alert, Workload } from "../types";

export default function AlertsPanel({
  alerts,
  workloads,
  onResolve,
  resolvingId,
}: {
  alerts: Alert[];
  workloads: Workload[];
  onResolve?: (alert: Alert) => void;
  resolvingId?: number | null;
}) {
  const nameOf = (id: number) =>
    workloads.find((w) => w.id === id)?.name ?? `workload #${id}`;

  const open = alerts.filter((a) => !a.resolved_at);
  const resolved = alerts.filter((a) => a.resolved_at);

  const renderAlert = (a: Alert) => (
    <li
      key={a.id}
      className={`alert ${a.resolved_at ? "alert-resolved" : "alert-open"}`}
    >
      <div className="alert-head">
        <span className="alert-rule">
          <span className={`sev sev-${a.severity}`}>{a.severity}</span>
          {a.rule}
          {a.detector && a.detector !== "threshold" ? (
            <span
              className="detector-tag"
              title="raised by statistical detection"
            >
              {a.detector}
            </span>
          ) : null}
        </span>
        <span className="alert-time">
          {new Date(a.triggered_at).toLocaleTimeString()}
        </span>
      </div>
      <div className="alert-msg">{a.message}</div>
      {a.summary ? <div className="alert-summary">{a.summary}</div> : null}
      <div className="alert-foot">
        <span className="alert-meta">
          {nameOf(a.workload_id)}
          {a.resolved_at
            ? ` · resolved ${new Date(a.resolved_at).toLocaleTimeString()}`
            : null}
        </span>
        {onResolve && !a.resolved_at ? (
          <button
            className="alert-resolve"
            aria-label={`Resolve ${a.rule} alert for ${nameOf(a.workload_id)}`}
            disabled={resolvingId === a.id}
            onClick={() => onResolve(a)}
          >
            {resolvingId === a.id ? "Resolving…" : "Resolve"}
          </button>
        ) : null}
      </div>
    </li>
  );

  return (
    <div className="panel alerts-panel">
      <h3>
        Alerts
        {open.length > 0 ? <span className="badge">{open.length}</span> : null}
      </h3>

      <div className="alert-section-title">Active</div>
      {open.length === 0 ? (
        <p className="muted">No active alerts — all clear 🎉</p>
      ) : (
        <ul className="alert-list">{open.map(renderAlert)}</ul>
      )}

      {resolved.length > 0 ? (
        <>
          <div className="alert-section-title alert-section-resolved">
            Resolved
          </div>
          <ul className="alert-list">{resolved.map(renderAlert)}</ul>
        </>
      ) : null}
    </div>
  );
}
