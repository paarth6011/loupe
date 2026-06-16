import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import SeasonalBaselinePanel from "./SeasonalBaselinePanel";
import type { BaselineProfile } from "../types";

function latency(bucket: number): BaselineProfile {
  return { metric: "latency", bucket, center: 200, scale: 20, n: 50 };
}

describe("SeasonalBaselinePanel", () => {
  it("shows a learning state with no coverage when nothing is learned", () => {
    render(<SeasonalBaselinePanel baselines={[]} />);
    expect(screen.getByText(/needs ~3 weeks/i)).toBeInTheDocument(); // the badge
    expect(
      screen.getByText(/rolling-window detector is used/i),
    ).toBeInTheDocument(); // the empty-state copy
    // No active coverage badge until at least one hour is learned.
    expect(screen.queryByText(/seasonal detection active/i)).toBeNull();
  });

  it("reports coverage once hours are learned", () => {
    render(
      <SeasonalBaselinePanel
        baselines={[latency(8), latency(9), latency(10)]}
      />,
    );
    expect(
      screen.getByText(/seasonal detection active · 3\/24h/i),
    ).toBeInTheDocument();
    // The learning copy is gone once the chart is shown.
    expect(screen.queryByText(/needs ~3 weeks/i)).toBeNull();
  });

  it("counts only latency buckets toward coverage", () => {
    const cost: BaselineProfile = {
      metric: "cost",
      bucket: 9,
      center: 0.01,
      scale: 0.002,
      n: 40,
    };
    render(<SeasonalBaselinePanel baselines={[latency(9), cost]} />);
    expect(
      screen.getByText(/seasonal detection active · 1\/24h/i),
    ).toBeInTheDocument();
  });
});
