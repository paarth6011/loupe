import { useEffect, useState } from "react";

import { listMonitors, updateMonitor } from "../api/monitors";
import type { Monitor } from "../types";

function fmt(n: number, integer: boolean): string {
  return integer ? String(Math.round(n)) : String(n);
}

export default function MonitorsPanel({
  workloadId,
  workloadName,
  onClose,
  onError,
}: {
  workloadId: number;
  workloadName: string;
  onClose: () => void;
  onError: (e: unknown) => void;
}) {
  const [monitors, setMonitors] = useState<Monitor[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [savingRule, setSavingRule] = useState<string | null>(null);

  // Load the full rule set for this workload (overrides merged onto defaults).
  useEffect(() => {
    let active = true;
    listMonitors(workloadId)
      .then((ms) => {
        if (!active) return;
        setMonitors(ms);
        setDrafts(
          Object.fromEntries(
            ms.map((m) => [
              m.rule,
              m.threshold == null ? "" : String(m.threshold),
            ]),
          ),
        );
      })
      .catch(onError);
    return () => {
      active = false;
    };
  }, [workloadId, onError]);

  async function patch(
    rule: string,
    body: { enabled?: boolean; threshold?: number | null },
  ) {
    setSavingRule(rule);
    try {
      const updated = await updateMonitor(workloadId, rule, body);
      setMonitors((cur) => cur.map((m) => (m.rule === rule ? updated : m)));
      setDrafts((d) => ({
        ...d,
        [rule]: updated.threshold == null ? "" : String(updated.threshold),
      }));
    } catch (e) {
      onError(e);
    } finally {
      setSavingRule(null);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Monitors — {workloadName}</h3>
          <button onClick={onClose}>Close</button>
        </div>
        <p className="muted modal-sub">
          Per-workload overrides. Leave a threshold blank to use the global
          default; turning a rule off mutes it and clears its active alerts.
        </p>
        <table className="monitors-table">
          <thead>
            <tr>
              <th>Rule</th>
              <th>On</th>
              <th>Threshold</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {monitors.map((m) => {
              const draft = drafts[m.rule] ?? "";
              const overridden = m.threshold != null;
              const changed =
                draft !== (m.threshold == null ? "" : String(m.threshold));
              return (
                <tr key={m.rule} className={m.enabled ? "" : "monitor-off"}>
                  <td>
                    <div className="monitor-label">{m.label}</div>
                    <div className="muted monitor-rule">
                      {m.rule}
                      {m.detector === "zscore" ? (
                        <span className="detector-tag">zscore</span>
                      ) : null}
                    </div>
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      checked={m.enabled}
                      aria-label={`${m.rule} enabled`}
                      onChange={(e) =>
                        patch(m.rule, { enabled: e.target.checked })
                      }
                    />
                  </td>
                  <td>
                    <div className="monitor-thr">
                      <input
                        type="number"
                        min={0}
                        step={m.integer ? 1 : "any"}
                        value={draft}
                        placeholder={fmt(m.default_threshold, m.integer)}
                        aria-label={`${m.rule} threshold`}
                        disabled={!m.enabled}
                        onChange={(e) =>
                          setDrafts((d) => ({ ...d, [m.rule]: e.target.value }))
                        }
                      />
                      <span className="monitor-unit">{m.unit}</span>
                    </div>
                    <div className="muted monitor-default">
                      {overridden ? "custom" : "default"} ·{" "}
                      {fmt(m.default_threshold, m.integer)} {m.unit}
                    </div>
                  </td>
                  <td>
                    <button
                      disabled={!changed || savingRule === m.rule}
                      onClick={() =>
                        patch(m.rule, {
                          threshold: draft === "" ? null : Number(draft),
                        })
                      }
                    >
                      {savingRule === m.rule ? "…" : "Save"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
