/**
 * InfographicCard — renders structured infographic JSON as a visual component.
 * Shape: { title, subtitle, key_stats:[{label,value,unit}],
 *          sections:[{heading,points}], chart:{type,labels,values,title}, source_note }
 */
import { useRef } from 'react';

const PALETTE = ['#6366f1', '#34d399', '#fbbf24', '#f87171', '#60a5fa', '#a78bfa', '#22d3ee', '#fb923c'];

function BarChart({ data }) {
  const { title = '', labels = [], values = [] } = data;
  if (!labels.length || !values.length) return null;

  const W = 480, H = 210, PAD = { top: 24, right: 16, bottom: 42, left: 44 };
  const chartW = W - PAD.left - PAD.right;
  const chartH = H - PAD.top - PAD.bottom;
  const maxVal = Math.max(...values, 1);
  const barW = chartW / labels.length;

  return (
    <div className="rounded-lg border border-line bg-inset p-3">
      {title && <p className="mb-2 text-xs font-medium text-ink">{title}</p>}
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={title}>
        {[0, 0.25, 0.5, 0.75, 1].map((pct) => {
          const y = PAD.top + chartH * (1 - pct);
          return (
            <g key={pct}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y} y2={y} stroke="var(--color-line)" strokeWidth="0.5" />
              <text x={PAD.left - 6} y={y + 4} textAnchor="end" fontSize="9" fill="var(--color-ink-subtle)">
                {Math.round(maxVal * pct)}
              </text>
            </g>
          );
        })}
        {values.map((val, i) => {
          const barH = (val / maxVal) * chartH;
          const x = PAD.left + i * barW + barW * 0.15;
          const y = PAD.top + chartH - barH;
          const color = PALETTE[i % PALETTE.length];
          return (
            <g key={i}>
              <rect x={x} y={y} width={barW * 0.7} height={barH} fill={color} rx="3" opacity="0.9" />
              <text x={x + barW * 0.35} y={y - 4} textAnchor="middle" fontSize="10" fill={color} fontWeight="600">{val}</text>
              <text x={x + barW * 0.35} y={H - PAD.bottom + 14} textAnchor="middle" fontSize="9" fill="var(--color-ink-subtle)">
                {(labels[i] || '').length > 10 ? labels[i].slice(0, 9) + '…' : labels[i]}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function PieChart({ data }) {
  const { title = '', labels = [], values = [] } = data;
  if (!labels.length || !values.length) return null;

  const total = values.reduce((a, b) => a + b, 0) || 1;
  const R = 78, CX = 100, CY = 100;
  const slices = [];
  values.reduce((cursor, val, i) => {
    const ratio = val / total;
    const end = cursor + ratio * 2 * Math.PI;
    slices.push({ ratio, start: cursor, end, color: PALETTE[i % PALETTE.length], label: labels[i] });
    return end;
  }, -Math.PI / 2);

  const arc = (cx, cy, r, start, end) => {
    const s = { x: cx + r * Math.cos(start), y: cy + r * Math.sin(start) };
    const e = { x: cx + r * Math.cos(end), y: cy + r * Math.sin(end) };
    const large = end - start > Math.PI ? 1 : 0;
    return `M ${cx} ${cy} L ${s.x} ${s.y} A ${r} ${r} 0 ${large} 1 ${e.x} ${e.y} Z`;
  };

  return (
    <div className="rounded-lg border border-line bg-inset p-3">
      {title && <p className="mb-2 text-xs font-medium text-ink">{title}</p>}
      <div className="flex flex-wrap items-center gap-4">
        <svg viewBox="0 0 200 200" className="h-40 w-40 shrink-0" role="img" aria-label={title}>
          {slices.map((s, i) => (
            <path key={i} d={arc(CX, CY, R, s.start, s.end)} fill={s.color} opacity="0.9" stroke="var(--color-surface)" strokeWidth="1.5" />
          ))}
        </svg>
        <ul className="space-y-1 text-xs">
          {slices.map((s, i) => (
            <li key={i} className="flex items-center gap-2 text-ink-muted">
              <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: s.color }} />
              <span className="text-ink">{s.label}</span>
              <span className="text-ink-subtle">{(s.ratio * 100).toFixed(1)}%</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export default function InfographicCard({ content }) {
  const cardRef = useRef(null);

  let data = {};
  try {
    data = typeof content === 'string' ? JSON.parse(content) : content;
  } catch {
    return (
      <div className="rounded-lg border border-danger/30 bg-danger-soft p-3 text-xs text-ink-muted">
        <p className="mb-1 font-medium text-danger">Could not render infographic — raw data:</p>
        <pre className="max-h-60 overflow-auto font-mono text-[11px]">{content}</pre>
      </div>
    );
  }

  const { title, subtitle, key_stats = [], sections = [], chart = {}, source_note } = data;
  const hasChart = chart?.labels?.length > 0 && chart?.values?.length > 0;

  return (
    <div ref={cardRef} className="infographic-card space-y-4 rounded-xl border border-line bg-surface-2 p-5">
      <div>
        <h3 className="text-lg font-semibold tracking-tight text-ink">{title || 'Infographic'}</h3>
        {subtitle && <p className="mt-0.5 text-sm text-ink-muted">{subtitle}</p>}
      </div>

      {key_stats.length > 0 && (
        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {key_stats.map((stat, i) => (
            <div
              key={i}
              className="rounded-lg border border-line bg-surface p-3"
              style={{ borderTopColor: PALETTE[i % PALETTE.length], borderTopWidth: 2 }}
            >
              <div className="text-xl font-semibold text-ink">
                {stat.value}
                {stat.unit && <span className="ml-1 text-xs font-medium text-ink-subtle">{stat.unit}</span>}
              </div>
              <div className="mt-0.5 text-xs text-ink-muted">{stat.label}</div>
            </div>
          ))}
        </div>
      )}

      {hasChart && (chart.type === 'pie' ? <PieChart data={chart} /> : <BarChart data={chart} />)}

      {sections.map((sec, i) => (
        <div key={i}>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-ink">{sec.heading}</h4>
          <ul className="mt-1.5 space-y-1 text-sm text-ink-muted">
            {(sec.points || []).map((pt, j) => (
              <li key={j} className="flex gap-2">
                <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-accent" />
                {pt}
              </li>
            ))}
          </ul>
        </div>
      ))}

      {source_note && <p className="border-t border-line pt-3 text-[11px] text-ink-subtle">{source_note}</p>}
    </div>
  );
}
