import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Workload } from "../types";
import AlertsPanel from "./AlertsPanel";

const workloads: Workload[] = [
  { id: 1, name: "gpt-4o-chat", created_at: "2026-01-01T00:00:00Z" },
];

describe("AlertsPanel", () => {
  it("shows an empty state when there are no alerts", () => {
    render(<AlertsPanel alerts={[]} workloads={workloads} />);
    expect(screen.getByText(/all clear/i)).toBeInTheDocument();
  });

  it("renders an alert with its rule and workload name", () => {
    render(
      <AlertsPanel
        alerts={[
          {
            id: 1,
            workload_id: 1,
            rule: "high_latency",
            message: "latency 3000ms exceeded threshold 1000ms",
            triggered_at: "2026-01-01T00:00:00Z",
            resolved_at: null,
          },
        ]}
        workloads={workloads}
      />,
    );
    expect(screen.getByText("high_latency")).toBeInTheDocument();
    expect(screen.getByText("gpt-4o-chat")).toBeInTheDocument();
  });
});
