import React from 'react';

/** Dependency-free SVG charts that inherit the editorial theme tokens. */

export function Sparkline({ values = [], width = 240, height = 56, stroke = 'var(--accent-primary)', label }) {
  if (!values.length) return <div className="chart-empty" style={{ height }}>No data yet</div>;
  const max = Math.max(...values, 1);
  const step = values.length > 1 ? width / (values.length - 1) : width;
  const pts = values.map((v, i) => [i * step, height - 4 - (v / max) * (height - 8)]);
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
  const area = `${line} L${width},${height} L0,${height} Z`;
  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={label}>
      <path d={area} fill={stroke} opacity="0.12" />
      <path d={line} fill="none" stroke={stroke} strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>
  );
}

/** Horizontal bar list: [{label, value, hint}] */
export function BarList({ items = [], format = (v) => v, color = 'var(--accent-primary)', onSelect }) {
  const max = Math.max(...items.map((i) => i.value), 1);
  if (!items.length) return <div className="chart-empty">No data yet</div>;
  return (
    <ul className="bar-list">
      {items.map((item) => (
        <li key={item.label}>
          <button type="button" className="bar-row" onClick={() => onSelect?.(item)} disabled={!onSelect}>
            <span className="bar-label">{item.label}</span>
            <span className="bar-track">
              <span className="bar-fill" style={{ width: `${(item.value / max) * 100}%`, background: item.color || color }} />
            </span>
            <span className="bar-value">{format(item.value)}</span>
          </button>
          {item.hint && <div className="bar-hint">{item.hint}</div>}
        </li>
      ))}
    </ul>
  );
}

/** 100%-stacked sentiment bar for one row: {positive, neutral, negative} */
export function SentimentBar({ positive = 0, neutral = 0, negative = 0 }) {
  const total = positive + neutral + negative || 1;
  const seg = (n) => `${(n / total) * 100}%`;
  return (
    <div className="sentiment-bar" role="img" aria-label={`${positive} positive, ${neutral} neutral, ${negative} negative`}>
      <span className="seg seg-positive" style={{ width: seg(positive) }} title={`${positive} positive`} />
      <span className="seg seg-neutral" style={{ width: seg(neutral) }} title={`${neutral} neutral`} />
      <span className="seg seg-negative" style={{ width: seg(negative) }} title={`${negative} negative`} />
    </div>
  );
}

/** Vertical column chart for a time series: [{label, value}] */
export function ColumnChart({ items = [], height = 120, color = 'var(--accent-primary)', labelEvery = 6 }) {
  if (!items.length) return <div className="chart-empty" style={{ height }}>No data yet</div>;
  const max = Math.max(...items.map((i) => i.value), 1);
  const w = 100 / items.length;
  return (
    <div className="column-chart">
      <svg viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" style={{ height }} role="img" aria-label="Articles per hour">
        {items.map((item, i) => {
          const h = (item.value / max) * (height - 4);
          return (
            <rect key={i} x={i * w + w * 0.15} y={height - h} width={w * 0.7} height={Math.max(h, item.value ? 1 : 0)} fill={color} rx="0.6">
              <title>{`${item.label}: ${item.value}`}</title>
            </rect>
          );
        })}
      </svg>
      <div className="column-axis">
        {items.map((item, i) => (
          <span key={i} style={{ width: `${w}%` }}>{i % labelEvery === 0 ? item.label : ''}</span>
        ))}
      </div>
    </div>
  );
}

/** Ring gauge for a 0..1 ratio */
export function Ring({ value, size = 64, label }) {
  const pct = value === null || value === undefined ? null : Math.max(0, Math.min(1, value));
  const r = size / 2 - 6;
  const c = 2 * Math.PI * r;
  return (
    <div className="ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--border-subtle)" strokeWidth="6" />
        {pct !== null && (
          <circle
            cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--accent-emerald)" strokeWidth="6"
            strokeDasharray={`${pct * c} ${c}`} strokeLinecap="round" transform={`rotate(-90 ${size / 2} ${size / 2})`}
          />
        )}
      </svg>
      <span className="ring-value">{pct === null ? '—' : `${Math.round(pct * 100)}%`}</span>
      {label && <span className="sr-only">{label}</span>}
    </div>
  );
}
