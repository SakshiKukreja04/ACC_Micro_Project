import React, { useEffect, useRef, useState } from 'react';
import apiService from '../services/api';
import { Ring, Sparkline } from './charts';
import { formatSeconds } from './ui';

const POLL_MS = 5000;

const STATUS_TEXT = { up: 'Healthy', degraded: 'Degraded', down: 'Down' };

export function MonitorPanel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [checkedAt, setCheckedAt] = useState(null);
  const [paused, setPaused] = useState(false);
  const timer = useRef(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      if (document.hidden || paused) return;
      try {
        const d = await apiService.getMonitoring();
        if (!alive) return;
        setData(d);
        setError(null);
        setCheckedAt(new Date());
      } catch (e) {
        if (alive) setError(e.message || 'Backend unreachable');
      }
    };
    tick();
    timer.current = setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      clearInterval(timer.current);
    };
  }, [paused]);

  if (!data && error) {
    return (
      <div className="monitor">
        <div className="monitor-banner status-down">
          <strong>The backend API is not responding.</strong> Check the container with <code>docker compose ps</code> and <code>docker compose logs backend</code>.
        </div>
      </div>
    );
  }
  if (!data) return <div className="explainer-loading" style={{ marginTop: 40 }}>Probing services…</div>;

  const unhealthy = data.services.filter((s) => s.status !== 'up');
  const api = data.api;
  const p = data.pipeline || {};
  const sc = p.status_counts || {};
  const grafana = import.meta.env.VITE_GRAFANA_URL || data.links.grafana;
  const prometheus = import.meta.env.VITE_PROMETHEUS_URL || data.links.prometheus;

  return (
    <div className="monitor">
      <header className="monitor-head">
        <div>
          <h1 className="hero-title">System monitor</h1>
          <p className="hero-subtitle">
            Live health of every container, refreshed every {POLL_MS / 1000} seconds. Long-term history and alerts live in Grafana.
          </p>
        </div>
        <div className="monitor-links">
          <a className="btn-secondary" href={grafana} target="_blank" rel="noopener noreferrer">Open Grafana ↗</a>
          <a className="btn-secondary" href={`${prometheus}/alerts`} target="_blank" rel="noopener noreferrer">Prometheus alerts ↗</a>
          <a className="btn-secondary" href={`${window.location.protocol}//${window.location.hostname}:8000/docs`} target="_blank" rel="noopener noreferrer">API docs ↗</a>
        </div>
      </header>

      <div className={`monitor-banner status-${data.overall_status === 'healthy' ? 'up' : data.overall_status === 'down' ? 'down' : 'degraded'}`} role="status">
        <span className="pulse-dot" aria-hidden="true" />
        <div>
          <strong>
            {unhealthy.length === 0
              ? `All ${data.services.length} services are healthy.`
              : `${unhealthy.length} of ${data.services.length} services need attention: ${unhealthy.map((s) => s.name).join(', ')}.`}
          </strong>
          <span className="monitor-checked">
            Checked {checkedAt?.toLocaleTimeString()} in {data.probe_ms} ms · backend v{data.version} up {formatSeconds(data.uptime_seconds)}
            {error && ` · last refresh failed: ${error}`}
          </span>
        </div>
        <button type="button" className="btn-action-ghost" onClick={() => setPaused((x) => !x)}>
          {paused ? 'Resume' : 'Pause'}
        </button>
      </div>

      <section className="service-grid" aria-label="Services">
        {data.services.map((s) => (
          <div key={s.name} className={`service-tile status-${s.status}`}>
            <div className="service-top">
              <span className="service-dot" aria-hidden="true" />
              <span className="service-name">{s.name}</span>
              <span className="service-status">{STATUS_TEXT[s.status]}</span>
            </div>
            <div className="service-kind">{s.kind}{s.latency_ms != null && ` — ${s.latency_ms} ms`}</div>
            <div className="service-detail">{s.detail}</div>
          </div>
        ))}
      </section>

      <div className="monitor-grid">
        <section className="panel">
          <div className="panel-head">
            <h2>API traffic</h2>
            <p>Last 10 minutes, excluding health checks and metric scrapes.</p>
          </div>
          <dl className="kpi-row">
            <div><dt>Requests / min</dt><dd>{api.requests_per_minute}</dd></div>
            <div><dt>p95 latency</dt><dd>{api.p95_ms} ms</dd></div>
            <div><dt>p99 latency</dt><dd>{api.p99_ms} ms</dd></div>
            <div><dt>Server errors</dt><dd className={api.error_rate > 0.01 ? 'kpi-bad' : ''}>{(api.error_rate * 100).toFixed(1)}%</dd></div>
          </dl>
          <div className="spark-pair">
            <div>
              <span className="spark-label">Requests per 20 s</span>
              <Sparkline values={api.series.map((s) => s.requests)} label="Requests over time" />
            </div>
            <div>
              <span className="spark-label">p95 latency per 20 s</span>
              <Sparkline values={api.series.map((s) => s.p95_ms)} stroke="var(--accent-amber)" label="Latency over time" />
            </div>
          </div>
          {api.top_endpoints.length > 0 && (
            <table className="mini-table">
              <thead><tr><th>Endpoint</th><th>Calls</th><th>Avg</th><th>p95</th></tr></thead>
              <tbody>
                {api.top_endpoints.map((e) => (
                  <tr key={e.endpoint}><td><code>{e.endpoint}</code></td><td>{e.requests}</td><td>{e.avg_ms} ms</td><td>{e.p95_ms} ms</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>Processing pipeline</h2>
            <p>From feed to AI briefing. The queue is PostgreSQL rows claimed with <code>FOR UPDATE SKIP LOCKED</code>.</p>
          </div>
          <div className="flow" role="img" aria-label="Pipeline flow">
            <div className="flow-node">
              <span className="flow-title">Collector</span>
              <span className="flow-num">{p.ingested_last_hour ?? 0}</span>
              <span className="flow-sub">stored in the last hour</span>
            </div>
            <span className="flow-arrow" aria-hidden="true" />
            <div className={`flow-node ${sc.pending > 50 ? 'flow-warn' : ''}`}>
              <span className="flow-title">Queue</span>
              <span className="flow-num">{(sc.pending || 0) + (sc.processing || 0)}</span>
              <span className="flow-sub">{sc.pending || 0} waiting, {sc.processing || 0} in progress</span>
            </div>
            <span className="flow-arrow" aria-hidden="true" />
            <div className="flow-node">
              <span className="flow-title">AI worker</span>
              <span className="flow-num">{p.completed_last_hour ?? 0}</span>
              <span className="flow-sub">summarised in the last hour</span>
            </div>
          </div>
          <dl className="kpi-row kpi-small">
            <div><dt>Completed</dt><dd>{sc.completed || 0}</dd></div>
            <div><dt>Failed</dt><dd className={sc.failed ? 'kpi-bad' : ''}>{sc.failed || 0}</dd></div>
            <div><dt>Feed → summary</dt><dd>{formatSeconds(p.avg_ingest_to_summary_seconds)}</dd></div>
            <div><dt>Oldest waiting</dt><dd>{formatSeconds(p.oldest_pending_age_seconds)}</dd></div>
          </dl>
          <dl className="kpi-row kpi-small">
            <div><dt>Worker processor</dt><dd>{data.worker.processor || '—'}</dd></div>
            <div><dt>Avg job time</dt><dd>{data.worker.avg_job_seconds != null ? `${data.worker.avg_job_seconds}s` : '—'}</dd></div>
            <div><dt>Retries</dt><dd>{data.worker.jobs_retried}</dd></div>
            <div><dt>Crash recoveries</dt><dd>{data.worker.jobs_recovered}</dd></div>
          </dl>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>Feed sources</h2>
            <p>
              {data.collector.reachable
                ? `${data.collector.cycles} collection cycles, last one ${formatSeconds(data.collector.seconds_since_last_cycle)} ago.`
                : 'Collector metrics are unreachable.'}
            </p>
          </div>
          {data.collector.sources.length ? (
            <table className="mini-table">
              <thead><tr><th>Source</th><th>Fetched</th><th>New</th><th>Errors</th><th>Last OK</th></tr></thead>
              <tbody>
                {data.collector.sources.map((s) => (
                  <tr key={s.source} className={s.errors && !s.last_success_age ? 'row-bad' : ''}>
                    <td>{s.source}</td><td>{s.fetched}</td><td>{s.inserted}</td><td>{s.errors}</td>
                    <td>{s.last_success_age != null ? `${formatSeconds(s.last_success_age)} ago` : 'never'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="empty-subtext">No collection cycle has finished yet.</p>}
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>AI, search and cache</h2>
          </div>
          <div className="ai-stats">
            <div className="ring-stat">
              <Ring value={data.cache.hit_ratio} label="Cache hit ratio" />
              <div><strong>Cache hit ratio</strong><span>{data.cache.hits} hits, {data.cache.misses} misses</span></div>
            </div>
            <div className="ring-stat">
              <Ring value={p.avg_grounding_score} label="Average Fact-Grounding" />
              <div><strong>Fact-Grounding</strong><span>Average share of summary words found in the source</span></div>
            </div>
          </div>
          <dl className="kpi-row kpi-small">
            <div><dt>Vectors</dt><dd>{data.vector.vectors}</dd></div>
            <div><dt>Story clusters</dt><dd>{data.vector.jobs?.story_clustering?.clusters ?? 0}</dd></div>
            <div><dt>Readers</dt><dd>{p.active_readers ?? 0}</dd></div>
            <div><dt>Bookmarks</dt><dd>{p.bookmarks ?? 0}</dd></div>
          </dl>
          <p className="monitor-note">Embedding model: <code>{data.vector.embedding_model}</code></p>
          {data.llm.operations.length > 0 ? (
            <table className="mini-table">
              <thead><tr><th>Groq operation</th><th>Calls (1h)</th><th>Errors</th><th>Avg</th></tr></thead>
              <tbody>
                {data.llm.operations.map((o) => (
                  <tr key={o.operation}><td>{o.operation}</td><td>{o.calls}</td><td>{o.errors}</td><td>{o.avg_ms} ms</td></tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="monitor-note">
              {data.llm.configured ? 'No Groq calls in the last hour.' : 'Groq is not configured — summaries, chat and briefings use offline fallbacks.'}
            </p>
          )}
        </section>
      </div>
    </div>
  );
}

export default MonitorPanel;
