import type { Alert, Workload } from "../types";

export default function AlertsPanel({
  alerts,
  workloads,
}: {
  alerts: Alert[];
  workloads: Workload[];
}) {
  const nameOf = (id: number) =>
    workloads.find((w) => w.id === id)?.name ?? `workload #${id}`;

  return (
    <div className="panel alerts-panel">
      <h3>
        Alerts
        {alerts.length > 0 ? <span className="badge">{alerts.length}</span> : null}
      </h3>
      {alerts.length === 0 ? (
        <p className="muted">No alerts — all clear 🎉</p>
      ) : (
        <ul className="alert-list">
          {alerts.map((a) => (
            <li
              key={a.id}
              className={`alert ${a.resolved_at ? "alert-resolved" : "alert-open"}`}
            >
              <div className="alert-head">
                <span className="alert-rule">
                  <span className={`sev sev-${a.severity}`}>{a.severity}</span>
                  {a.rule}
                </span>
                <span className="alert-time">
                  {new Date(a.triggered_at).toLocaleTimeString()}
                </span>
              </div>
              <div className="alert-msg">{a.message}</div>
              {a.summary ? <div className="alert-summary">{a.summary}</div> : null}
              <div className="alert-meta">{nameOf(a.workload_id)}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
