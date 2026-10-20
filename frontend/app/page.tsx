'use client';
import {useEffect, useState} from 'react';

const API = (process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api') + '/beta';
const sample = JSON.stringify([{
  name: 'Refund policy', question: 'How long do I have to request a refund?',
  reference: 'REPLACE with the approved refund policy from your agent knowledge base.',
  expected: 'State the refund window accurately without inventing conditions.',
  required_literals: [], forbidden_literals: [], require_citations: false,
}], null, 2);
type Settings = {judge_configured: boolean; judge_model: string; pipeline: string};
type Result = {
  name: string; status: string; answer?: string; error?: string; answer_latency_ms?: number;
  case: {reference: string; expected: string; question: string};
  checks?: {check: string; value?: string; passed: boolean}[];
  judge?: {rationale: string; answer_quote: string; reference_quote: string};
};
type Run = {
  id: string; status: string; results?: Result[];
  summary: {pass: number; fail: number; error: number; inconclusive: number; scored: number; pass_rate: number | null};
};
async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(API + path, body === undefined ? {signal: AbortSignal.timeout(15000)} : {
    signal: AbortSignal.timeout(15000),
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  return data;
}
export default function Home() {
  const [settings, setSettings] = useState<Settings>();
  const [history, setHistory] = useState<Run[]>([]);
  const [run, setRun] = useState<Run>();
  const [name, setName] = useState('nRouter customer support');
  const [endpoint, setEndpoint] = useState('http://127.0.0.1:4175/api/chat');
  const [authEnv, setAuthEnv] = useState('');
  const [cases, setCases] = useState(sample);
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [baseline, setBaseline] = useState('');
  const [comparison, setComparison] = useState('');
  const active = run?.status === 'pending' || run?.status === 'running';
  async function refresh() {
    try {
      const [config, runs] = await Promise.all([request<Settings>('/settings'), request<Run[]>('/runs')]);
      setSettings(config); setHistory(runs); setError('');
    } catch (e) { setError(String(e)); }
  }
  useEffect(() => { void refresh(); }, []);
  useEffect(() => {
    if (!active || !run) return;
    let disposed = false;
    let fetching = false;
    const timer = setInterval(() => {
      if (fetching) return;
      fetching = true;
      request<Run>('/runs/' + run.id).then(updated => {
        if (disposed) return;
        setRun(updated);
        if (!['pending', 'running'].includes(updated.status)) void refresh();
      }).catch(e => { if (!disposed) setError(String(e)); }).finally(() => { fetching = false; });
    }, 1500);
    return () => { disposed = true; clearInterval(timer); };
  }, [run?.id, active]);
  async function launch() {
    setBusy(true); setError(''); setComparison('');
    try {
      const parsed = JSON.parse(cases);
      if (cases.includes('REPLACE with')) throw new Error('Replace the sample reference with your approved source before running.');
      setRun(await request<Run>('/runs', {
        agent_name: name, endpoint, auth_env: authEnv || null, cases: parsed, send_to_judge: consent,
      }));
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(run, null, 2)], {type: 'application/json'}));
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = `memoryscope-${run?.id}.json`; anchor.click();
    URL.revokeObjectURL(url);
  }
  return <main>
    <header><div><span className="eyebrow">MEMORYSCOPE / DEVELOPER BETA</span>
      <h1>Test your support agent against the facts.</h1>
      <p>Real agent responses. Explicit checks. Reference-grounded judgment.</p>
    </div><button onClick={refresh}>Refresh</button></header>
    {error && <div className="notice" role="alert">{error}</div>}
    <div className="notice">{settings?.judge_configured
      ? `Required judge: ${settings.judge_model} · ${settings.pipeline}`
      : 'Setup required: add NROUTER_API_KEY and NROUTER_JUDGE_MODEL to the root .env, then restart the backend.'}
      <p>This beta evaluates individual answers. It does not establish persistent-memory recall or tenant isolation.</p></div>
    <section className="two-col">
      <section className="panel"><h2>1. Connect your agent</h2>
        <label>Agent name<input value={name} onChange={e => setName(e.target.value)}/></label>
        <label>Chat endpoint<input type="url" value={endpoint} onChange={e => setEndpoint(e.target.value)}/></label>
        <p>The nRouter support-agent SSE format is supported. The origin must be allowlisted server-side.</p>
        <label>Agent credential environment variable (if needed)<input placeholder="MEMORYSCOPE_AGENT_SUPPORT_TOKEN" value={authEnv} onChange={e => setAuthEnv(e.target.value)}/></label>
        <p>Enter the variable name, never a secret. The judge key is configured separately on the server.</p>
        <h2>2. Define expected behavior</h2>
        <p>Provide 1–20 cases. References go only to the judge, not to your agent. Literal checks use case-insensitive substring matching.</p>
        <label>Import cases JSON<input type="file" accept=".json,application/json" onChange={async e => {
          const file = e.target.files?.[0];
          if (!file) return;
          if (file.size > 500000) { setError('File must be below 500 KB.'); return; }
          try { setCases(JSON.stringify(JSON.parse(await file.text()), null, 2)); }
          catch { setError('Invalid JSON file.'); }
        }}/></label>
        <label>Cases JSON<textarea rows={18} value={cases} onChange={e => setCases(e.target.value)}/></label>
        <label className="consent"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)}/>
          I approve sending these references and agent answers to nRouter for paid LLM evaluation. Reports are saved locally.</label>
        <button disabled={busy || active || !settings?.judge_configured || !consent} onClick={launch}>{busy ? 'Starting…' : 'Run evaluation'}</button>
      </section>
      <section className="panel"><h2>3. Inspect the evidence</h2>
        {!run && <p>Select a previous run or start an evaluation. No demo scores are mixed into these results.</p>}
        {run && <>
          <p><code>{run.id.slice(0, 8)}</code> · {run.status}</p>
          <p>{run.summary.pass} passed · {run.summary.fail} failed · {run.summary.error} errors · {run.summary.inconclusive} inconclusive</p>
          <p>Pass rate: {run.summary.pass_rate === null ? 'Not scored' : `${Math.round(run.summary.pass_rate * 100)}%`} ({run.summary.scored} scored cases; errors and inconclusive excluded)</p>
          <button onClick={download}>Export evidence JSON</button>
          {active && <button onClick={async () => {
            try { setRun(await request<Run>(`/runs/${run.id}/cancel`, {})); }
            catch (e) { setError(String(e)); }
          }}>Cancel remaining work</button>}
          {run.results?.map(result => <details key={result.name}>
            <summary>{result.name} — {result.status}</summary>
            <h3>Question</h3><p>{result.case.question}</p>
            <h3>Agent answer</h3><p>{result.answer || 'No complete answer received.'}</p>
            <h3>Approved reference</h3><p>{result.case.reference}</p>
            <h3>Expected behavior</h3><p>{result.case.expected}</p>
            {result.checks?.map((check, index) => <p key={index}>{check.passed ? 'PASS' : 'FAIL'}: {check.check} {check.value}</p>)}
            {result.judge && <><h3>Judge rationale</h3><p>{result.judge.rationale}</p>
              <blockquote>Answer: {result.judge.answer_quote}</blockquote>
              <blockquote>Reference: {result.judge.reference_quote}</blockquote></>}
            {result.error && <p role="alert">{result.error}</p>}
            {result.answer_latency_ms !== undefined && <small>Agent response time: {result.answer_latency_ms} ms (excludes judge)</small>}
          </details>)}
          <h3>Compare with a baseline</h3>
          <select aria-label="Baseline run" value={baseline} onChange={e => setBaseline(e.target.value)}>
            <option value="">Select completed run</option>
            {history.filter(r => r.status === 'completed' && r.id !== run.id).map(r => <option key={r.id} value={r.id}>{r.id.slice(0, 8)}</option>)}
          </select>
          <button disabled={!baseline || run.status !== 'completed'} onClick={async () => {
            try { setComparison(JSON.stringify(await request(`/compare/${baseline}/${run.id}`), null, 2)); }
            catch (e) { setError(String(e)); }
          }}>Compare identical suite</button>
          {comparison && <pre>{comparison}</pre>}
        </>}
        <h2>Run history</h2>
        {history.map(item => <div className="row" key={item.id}><button onClick={async () => {
          try { setRun(await request<Run>('/runs/' + item.id)); setComparison(''); }
          catch (e) { setError(String(e)); }
        }}>{item.id.slice(0, 8)}</button><span>{item.status}</span><span>{item.summary.scored} scored</span></div>)}
      </section>
    </section>
  </main>;
}
