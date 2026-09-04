import { useEffect, useState } from "react";

import type { DeliveryRun, Risk } from "./types";

const API = import.meta.env.VITE_API_URL ?? "";

export default function App() {
  const [source, setSource] = useState("demo");
  const [sources, setSources] = useState([{ id: "demo", label: "Demo", available: true }]);
  const [contexts, setContexts] = useState([{ external_id: "northstar", name: "Northstar Platform" }]);
  const [contextId, setContextId] = useState("northstar");
  const [run, setRun] = useState<DeliveryRun | null>(null);
  const [history, setHistory] = useState<DeliveryRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API}/api/sources`).then((response) => response.json()).then(setSources).catch(() => undefined);
  }, []);

  useEffect(() => {
    setRun(null);
    if (source === "demo") {
      setContexts([{ external_id: "northstar", name: "Northstar Platform" }]);
      setContextId("northstar");
      return;
    }
    fetch(`${API}/api/sources/${source}/contexts`)
      .then((response) => {
        if (!response.ok) throw new Error("Source is unavailable");
        return response.json();
      })
      .then((items) => {
        setContexts(items);
        if (items[0]) setContextId(items[0].external_id);
      })
      .catch(() => setContexts([]));
  }, [source]);

  async function requestAnalysis(endpoint: string, body?: object) {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API}${endpoint}`, {
        method: "POST",
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!response.ok) throw new Error("Analysis failed");
      const next = (await response.json()) as DeliveryRun;
      setRun(next);
      await refreshHistory();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  }

  async function refreshHistory() {
    const response = await fetch(`${API}/api/runs?source=${source}&context_id=${contextId}`);
    if (response.ok) setHistory((await response.json()) as DeliveryRun[]);
  }

  function analyze() {
    return source === "demo"
      ? requestAnalysis("/api/demo/reset")
      : requestAnalysis("/api/analyze", { source, context_id: contextId });
  }

  function advanceDemo() {
    return requestAnalysis("/api/demo/advance");
  }

  async function openRun(runId: string) {
    const response = await fetch(`${API}/api/runs/${runId}`);
    if (response.ok) setRun((await response.json()) as DeliveryRun);
  }

  const period = run ? formatPeriod(run.assessment.period) : "CURRENT REVIEW";
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-mark">ADI</div>
        <div className="brand-copy"><strong>Delivery Intelligence</strong><span>Evidence before narrative</span></div>
        <nav><a className="active" href="#review">Review</a><a href="#history">Run history</a><a href="#policies">Policies</a></nav>
        <div className="boundary-note"><span>Read-only boundary</span>No tracker writes. No release verdicts.</div>
      </aside>

      <main>
        <header>
          <div><div className="eyebrow">DELIVERY REVIEW · {period}</div><h1>What changed since the previous review?</h1><p>Deterministic flow evidence, grounded policy, and bounded management actions.</p></div>
          <div className="mode-chip"><i /> {run?.assessment.mode ?? "replay"} mode</div>
        </header>

        <section className="control-bar" id="review">
          <label>Source <span className="source-tabs">{sources.map((item) => <button type="button" key={item.id} className={source === item.id ? "selected" : ""} disabled={!item.available} onClick={() => setSource(item.id)}>{item.label}</button>)}</span></label>
          <label>Project <select value={contextId} onChange={(event) => setContextId(event.target.value)}>{contexts.map((item) => <option value={item.external_id} key={item.external_id}>{item.name}</option>)}</select></label>
          <button onClick={analyze} disabled={loading || contexts.length === 0}>{loading ? "Analyzing…" : "Analyze delivery"}</button>
        </section>

        {error && <div className="error">{error}</div>}
        {!run ? <EmptyState onRun={analyze} /> : <Assessment run={run} history={history} onAdvance={advanceDemo} onOpenRun={openRun} loading={loading} />}
      </main>
    </div>
  );
}

function EmptyState({ onRun }: { onRun: () => void }) {
  return <section className="empty-state"><span>Credential-free scenario</span><h2>Northstar moves from stable flow to material delivery risk.</h2><p>Analyze T1 first, then advance to T2 to inspect exact changes, evidence, policy, and actions.</p><button onClick={onRun}>Load current state</button></section>;
}

function Assessment({ run, history, onAdvance, onOpenRun, loading }: { run: DeliveryRun; history: DeliveryRun[]; onAdvance: () => void; onOpenRun: (id: string) => void; loading: boolean }) {
  const { assessment, analysis } = run;
  const visibleChanges = assessment.changes.filter((change) => ["ITEM_COMPLETED", "BLOCKER_APPEARED", "BLOCKER_RESOLVED", "WIP_LIMIT_CROSSED", "AGING_THRESHOLD_CROSSED", "DEPENDENCY_APPEARED"].includes(change.change_type));
  const verifyAging = assessment.flow_signals.filter((signal) => signal.signal_type === "VERIFY_QUEUE_AGING").length;
  const breachedBlockers = assessment.flow_signals.filter((signal) => signal.signal_type === "BLOCKER_SLA_EXCEEDED").length;
  return <>
    {assessment.uncertainties.map((uncertainty) => <div className="uncertainty" key={uncertainty}>{uncertainty}</div>)}
    {assessment.source === "demo" && assessment.current_state_only && <button className="advance-button" onClick={onAdvance} disabled={loading}>Advance to T2</button>}
    <section className="status-grid">
      <article className="status-card"><span>Overall delivery</span><div className={`status ${assessment.overall_delivery_status.toLowerCase()}`}><i /> {assessment.overall_delivery_status.replace("_", " ")}</div><p>{statusReason(assessment.overall_delivery_status, assessment.risks.length)}</p></article>
      <Metric label="WIP" value={`${analysis.metrics.wip} / ${analysis.metrics.wip_limit ?? "—"}`} detail={analysis.metrics.wip_limit && analysis.metrics.wip > analysis.metrics.wip_limit ? `Limit exceeded by ${analysis.metrics.wip - analysis.metrics.wip_limit}` : "Within configured limit"} hot={Boolean(analysis.metrics.wip_limit && analysis.metrics.wip > analysis.metrics.wip_limit)} />
      <Metric label="Aging items" value={String(analysis.metrics.aging_items)} detail={`${verifyAging} in Verify`} />
      <Metric label="Blocked" value={String(analysis.metrics.blocked_items)} detail={`${breachedBlockers} beyond SLA`} hot={breachedBlockers > 0} />
    </section>

    <div className="content-grid">
      <section className="panel changes-panel"><PanelTitle index="01" title="What changed" hint={assessment.current_state_only ? "Current state only" : `${visibleChanges.length} material deltas`} />
        {visibleChanges.length === 0 ? <p className="panel-empty">No temporal changes are available for this run.</p> : <div className="timeline">{visibleChanges.slice(0, 6).map((change) => <div className="change-row" key={`${change.change_type}-${change.item_id}`}><span className={`change-icon ${change.change_type.includes("RESOLVED") || change.change_type.includes("COMPLETED") ? "positive" : "negative"}`} /><div><strong>{friendlyChange(change.change_type)}</strong><p>{change.item_id ? `${shortId(change.item_id)} · ` : ""}{change.summary}</p></div></div>)}</div>}
      </section>

      <section className="panel attention-panel"><PanelTitle index="02" title="Needs attention" hint="Prioritized by severity" />
        {assessment.risks.slice(0, 4).map((risk, index) => <RiskRow risk={risk} rank={index + 1} key={`${risk.title}-${index}`} />)}
      </section>

      <section className="panel actions-panel"><PanelTitle index="03" title="Recommended actions" hint="Advisory · read-only" />
        {assessment.recommended_actions.slice(0, 4).map((action, index) => <div className="action-row" key={`${action.action_type}-${index}`}><b>0{index + 1}</b><div><strong>{action.action}</strong><p>{action.rationale}</p><details><summary>Evidence &amp; policy</summary><small>{action.evidence.join(", ")} · <PolicyLink source={action.policy_sources[0]} /></small></details></div></div>)}
      </section>

      <section className="panel history-panel" id="history"><PanelTitle index="04" title="Run history" hint="Snapshots + validated output" />
        {history.map((item) => <button className="history-row" type="button" onClick={() => onOpenRun(item.run_id)} key={item.run_id}><i className={item.run_id === run.run_id ? "current" : ""} /><div><strong>{item.run_id === run.run_id ? "Current assessment" : formatDate(item.created_at)}</strong><p>{item.assessment.current_state_only ? "Current state only" : `${item.assessment.changes.length} changes detected`}</p></div><span>{item.assessment.overall_delivery_status.replace("_", " ")}</span></button>)}
      </section>
    </div>
  </>;
}

function Metric({ label, value, detail, hot = false }: { label: string; value: string; detail: string; hot?: boolean }) { return <article className={`metric-card ${hot ? "hot" : ""}`}><span>{label}</span><strong>{value}</strong><p>{detail}</p></article>; }
function PanelTitle({ index, title, hint }: { index: string; title: string; hint: string }) { return <div className="panel-title"><span>{index}</span><h2>{title}</h2><em>{hint}</em></div>; }
function PolicyLink({ source }: { source?: string }) { return source ? <a id="policies" href={`${API}/api/policies/${encodeURIComponent(source)}`} target="_blank" rel="noreferrer">{source}</a> : <>No applicable policy</>; }
function RiskRow({ risk, rank }: { risk: Risk; rank: number }) { return <div className="risk-row"><b>{rank}</b><div><span className={`severity ${risk.severity}`}>{risk.severity}</span><strong>{risk.title}</strong><p>{risk.reason}</p><details><summary>Evidence &amp; policy</summary><small><u>Evidence</u> {risk.evidence.join(", ")} · <u>Policy</u> <PolicyLink source={risk.policy_sources[0]} /></small></details></div></div>; }

const shortId = (value: string) => value.split(":").at(-1);
const friendlyChange = (value: string) => value.toLowerCase().replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
const formatDate = (value: string) => new Intl.DateTimeFormat("en", { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: "UTC" }).format(new Date(value));
const formatPeriod = (period: { from_timestamp: string | null; to_timestamp: string }) => `${period.from_timestamp ? formatDate(period.from_timestamp) : "FIRST RUN"} — ${formatDate(period.to_timestamp)}`;
const statusReason = (status: string, risks: number) => status === "BLOCKED" ? "Structured evidence shows no viable delivery-flow path." : status === "AT_RISK" ? `${risks} policy-backed delivery risks require management attention.` : status === "ATTENTION" ? `${risks} delivery signals should be reviewed.` : "No material policy-backed delivery risk is present.";
