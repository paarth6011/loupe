import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import SummaryCards from "./SummaryCards";

describe("SummaryCards", () => {
  it("renders metric values from a summary", () => {
    render(
      <SummaryCards
        summary={{
          workload_id: 1,
          window: "1h",
          request_count: 42,
          error_count: 2,
          error_rate: 0.05,
          latency_p50_ms: 210,
          latency_p95_ms: 480,
          total_input_tokens: 0,
          total_output_tokens: 0,
          total_cost_usd: 0,
        }}
      />,
    );
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("5.0%")).toBeInTheDocument();
    expect(screen.getByText("210ms")).toBeInTheDocument();
    expect(screen.getByText("480ms")).toBeInTheDocument();
  });

  it("renders placeholders when there is no summary", () => {
    render(<SummaryCards summary={null} />);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});
