/**
 * InfographicCard — renders structured infographic JSON as a visual component.
 * Data shape:
 *   { title, subtitle, key_stats: [{label, value, unit}],
 *     sections: [{heading, points}], chart: {type, title, labels, values},
 *     source_note }
 */
import { useRef } from 'react';

// ── Colour palette (CSS vars already exist in App.css) ───────────────────────
const PALETTE = [
  '#6C63FF', '#4ECDC4', '#F7B731', '#FC5C65', '#45AAF2',
  '#26DE81', '#FD9644', '#A29BFE', '#74B9FF', '#55EFC4',
];

// ── SVG Bar Chart ─────────────────────────────────────────────────────────────
function BarChart({ data }) {
  const { title = '', labels = [], values = [] } = data;
  if (!labels.length || !values.length) return null;

  const W = 480, H = 200, PAD = { top: 24, right: 16, bottom: 40, left: 48 };
  const chartW = W - PAD.left - PAD.right;
  const chartH = H - PAD.top - PAD.bottom;
  const maxVal  = Math.max(...values, 1);
  const barW    = chartW / labels.length;

  return (
    <div className="infographic-chart-wrap">
      {title && <div className="infographic-chart-title">{title}</div>}
      <svg viewBox={`0 0 ${W} ${H}`} className="infographic-chart-svg" role="img" aria-label={title}>
        {/* Y-axis ticks */}
        {[0, 0.25, 0.5, 0.75, 1].map((pct) => {
          const y = PAD.top + chartH * (1 - pct);
          const val = Math.round(maxVal * pct);
          return (
            <g key={pct}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y} y2={y} stroke="var(--border)" strokeWidth="0.5" />
              <text x={PAD.left - 6} y={y + 4} textAnchor="end" fontSize="9" fill="var(--text-3)">{val}</text>
            </g>
          );
        })}
        {/* Bars */}
        {values.map((val, i) => {
          const barH  = (val / maxVal) * chartH;
          const x     = PAD.left + i * barW + barW * 0.15;
          const y     = PAD.top + chartH - barH;
          const color = PALETTE[i % PALETTE.length];
          return (
            <g key={i}>
              <rect x={x} y={y} width={barW * 0.7} height={barH} fill={color} rx="3" opacity="0.9" />
              {/* Value label on top */}
              <text x={x + barW * 0.35} y={y - 4} textAnchor="middle" fontSize="10" fill={color} fontWeight="600">
                {val}
              </text>
              {/* X-axis label */}
              <text
                x={x + barW * 0.35}
                y={H - PAD.bottom + 14}
                textAnchor="middle"
                fontSize="9"
                fill="var(--text-3)"
              >
                {(labels[i] || '').length > 10 ? labels[i].slice(0, 9) + '…' : labels[i]}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ── SVG Pie Chart ─────────────────────────────────────────────────────────────
function PieChart({ data }) {
  const { title = '', labels = [], values = [] } = data;
  if (!labels.length || !values.length) return null;

  const total = values.reduce((a, b) => a + b, 0) || 1;
  const R = 80, CX = 100, CY = 100;
  let angle = -Math.PI / 2;
  const slices = values.map((val, i) => {
    const ratio = val / total;
    const start = angle;
    angle += ratio * 2 * Math.PI;
    return { ratio, start, end: angle, color: PALETTE[i % PALETTE.length], label: labels[i], val };
  });

  const arc = (cx, cy, r, start, end) => {
    const s = { x: cx + r * Math.cos(start), y: cy + r * Math.sin(start) };
    const e = { x: cx + r * Math.cos(end),   y: cy + r * Math.sin(end) };
    const large = end - start > Math.PI ? 1 : 0;
    return `M ${cx} ${cy} L ${s.x} ${s.y} A ${r} ${r} 0 ${large} 1 ${e.x} ${e.y} Z`;
  };

  return (
    <div className="infographic-chart-wrap">
      {title && <div className="infographic-chart-title">{title}</div>}
      <div className="infographic-pie-row">
        <svg viewBox="0 0 200 200" className="infographic-pie-svg" role="img" aria-label={title}>
          {slices.map((s, i) => (
            <path key={i} d={arc(CX, CY, R, s.start, s.end)} fill={s.color} opacity="0.9" stroke="var(--surface-1)" strokeWidth="1.5" />
          ))}
        </svg>
        <ul className="infographic-pie-legend">
          {slices.map((s, i) => (
            <li key={i} className="infographic-pie-legend-item">
              <span className="infographic-pie-swatch" style={{ background: s.color }} />
              <span className="infographic-pie-label">{s.label}</span>
              <span className="infographic-pie-pct">{(s.ratio * 100).toFixed(1)}%</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

// ── Main InfographicCard ──────────────────────────────────────────────────────
export default function InfographicCard({ content, onExportPng }) {
  const cardRef = useRef(null);

  let data = {};
  try {
    data = typeof content === 'string' ? JSON.parse(content) : content;
  } catch {
    return (
      <div className="infographic-parse-error">
        <span>⚠</span>
        <p>Could not render infographic — raw data below:</p>
        <pre>{content}</pre>
      </div>
    );
  }

  const { title, subtitle, key_stats = [], sections = [], chart = {}, source_note } = data;
  const hasChart = chart?.labels?.length > 0 && chart?.values?.length > 0;

  const handleExport = () => {
    if (onExportPng) { onExportPng(cardRef.current); return; }
    // Fallback: print the card
    window.print();
  };

  return (
    <div className="infographic-card" ref={cardRef}>
      {/* Header */}
      <div className="infographic-header">
        <h2 className="infographic-title">{title || 'Infographic'}</h2>
        {subtitle && <p className="infographic-subtitle">{subtitle}</p>}
      </div>

      {/* Key Stats Tiles */}
      {key_stats.length > 0 && (
        <div className="infographic-stats">
          {key_stats.map((stat, i) => (
            <div key={i} className="infographic-stat-tile" style={{ '--accent': PALETTE[i % PALETTE.length] }}>
              <div className="infographic-stat-value">
                {stat.value}
                {stat.unit && <span className="infographic-stat-unit">{stat.unit}</span>}
              </div>
              <div className="infographic-stat-label">{stat.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Chart */}
      {hasChart && (
        chart.type === 'pie'
          ? <PieChart data={chart} />
          : <BarChart data={chart} />
      )}

      {/* Sections */}
      {sections.map((sec, i) => (
        <div key={i} className="infographic-section">
          <h3 className="infographic-section-heading">{sec.heading}</h3>
          <ul className="infographic-section-points">
            {(sec.points || []).map((pt, j) => (
              <li key={j} className="infographic-section-point">{pt}</li>
            ))}
          </ul>
        </div>
      ))}

      {/* Source note */}
      {source_note && (
        <div className="infographic-source-note">{source_note}</div>
      )}
    </div>
  );
}
