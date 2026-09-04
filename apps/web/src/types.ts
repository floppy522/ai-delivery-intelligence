export type Citation = { source_id?: string };

export type Change = {
  change_type: string;
  summary: string;
  item_id?: string;
  evidence: string[];
};

export type Signal = {
  signal_type: string;
  severity: string;
  summary: string;
  item_ids: string[];
  evidence: string[];
};

export type Risk = {
  title: string;
  severity: string;
  reason: string;
  evidence: string[];
  policy_sources: string[];
};

export type Action = {
  action_type: string;
  action: string;
  rationale: string;
  evidence: string[];
  policy_sources: string[];
};

export type DeliveryRun = {
  run_id: string;
  created_at: string;
  analysis: {
    metrics: { wip: number; wip_limit: number | null; aging_items: number; blocked_items: number; verify_items: number };
  };
  assessment: {
    project: string;
    source: string;
    mode: string;
    current_state_only: boolean;
    period: { from_timestamp: string | null; to_timestamp: string };
    overall_delivery_status: string;
    changes: Change[];
    flow_signals: Signal[];
    risks: Risk[];
    recommended_actions: Action[];
    escalations: Action[];
    uncertainties: string[];
  };
};
