import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import App from "./App";

afterEach(() => vi.restoreAllMocks());

const baseline = {
  run_id: "t1", created_at: "2026-09-03T09:00:00Z",
  analysis: { metrics: { wip: 7, wip_limit: 7, aging_items: 0, blocked_items: 1, verify_items: 1 } },
  assessment: {
    project: "Northstar Platform", source: "demo", mode: "replay", current_state_only: true,
    period: { from_timestamp: null, to_timestamp: "2026-09-03T09:00:00Z" },
    overall_delivery_status: "ATTENTION", changes: [], flow_signals: [], risks: [],
    recommended_actions: [], escalations: [],
    uncertainties: ["No previous snapshot available. Current-state analysis only."],
  },
};

const delta = {
  run_id: "t2", created_at: "2026-09-07T09:00:00Z",
  analysis: { metrics: { wip: 10, wip_limit: 7, aging_items: 4, blocked_items: 1, verify_items: 3 } },
  assessment: {
    project: "Northstar Platform", source: "demo", mode: "replay", current_state_only: false,
    period: { from_timestamp: "2026-09-03T09:00:00Z", to_timestamp: "2026-09-07T09:00:00Z" },
    overall_delivery_status: "AT_RISK",
    changes: [{ change_type: "WIP_LIMIT_CROSSED", summary: "WIP crossed", evidence: [] }],
    flow_signals: [{ signal_type: "BLOCKER_SLA_EXCEEDED", severity: "critical", summary: "blocked", item_ids: ["demo:NS-17"], evidence: ["relation:17"] }],
    risks: [{ title: "Blocker SLA exceeded", severity: "critical", reason: "NS-17 blocked 5 days", evidence: ["relation:17"], policy_sources: ["blocker-policy.md#critical-blocker-sla"] }],
    recommended_actions: [{ action_type: "ESCALATE_BLOCKER", action: "Escalate blocker ownership.", rationale: "SLA exceeded", evidence: ["relation:17"], policy_sources: ["blocker-policy.md#critical-blocker-sla"] }],
    escalations: [], uncertainties: [],
  },
};

test("shows first-run uncertainty then the credential-free temporal delta", async () => {
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify([{ id: "demo", label: "Demo", available: true }]), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(baseline), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify([baseline]), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(delta), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify([delta, baseline]), { status: 200 }));

  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Analyze delivery" }));
  expect(await screen.findByText(/No previous snapshot available/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Advance to T2" }));
  expect((await screen.findAllByText("AT RISK"))[0]).toBeInTheDocument();
  expect(screen.getByText("Blocker SLA exceeded")).toBeInTheDocument();
  expect(screen.getAllByText("Evidence & policy")).toHaveLength(2);
});
