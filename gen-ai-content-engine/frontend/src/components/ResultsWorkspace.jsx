import { useState, useCallback } from 'react';
import { OUTPUT_OPTS } from '../App';
import InfographicCard from './InfographicCard';
import VersionBanner from './VersionBanner';

// ── Icons ─────────────────────────────────────────────────────────────────────
function CopyIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
      <rect x="4.5" y="4.5" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.2" />
      <path d="M4.5 4.5V3a1 1 0 011-1h5a1 1 0 011 1v5a1 1 0 01-1 1H9" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  );
}
function CheckIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
      <path d="M2 6.5L5 9.5L11 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function DownloadIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
      <path d="M6.5 1v8M3.5 6.5l3 3 3-3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M1.5 11.5h10" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

// ── Text cleaners ─────────────────────────────────────────────────────────────
function cleanOutput(value) {
  return String(value ?? '')
    .replace(/\\n/g, '\n')
    .replace(/\\r/g, '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, '')
    .replace(/\u{FE0F}/gu, '')
    .replace(/[ \t]+\n/g, '\n')
    .trim();
}

function FormattedOutput({ content }) {
  return cleanOutput(content).split(/\n{2,}/).map((block, index) => {
    const lines = block.split('\n').map((l) => l.trim()).filter(Boolean);
    if (!lines.length) return null;
    const first = lines[0];
    const isHeading =
      lines.length === 1 &&
      (/^\[[A-Z ]+\]$/.test(first) ||
        /^(SLIDE\s+\d+:|EXECUTIVE SUMMARY|SITUATION OVERVIEW|STRATEGIC IMPERATIVE|GOVERNANCE|RECOMMENDED|CONCLUSION|CONTEXT|KEY FINDINGS|RISK|Tweet \d)/i.test(first) ||
        /^[A-Z][A-Z &/]{3,}:/.test(first) ||
        /^\d+\.\s+[A-Z]/.test(first));
    if (isHeading) {
      return <h3 className="results-content-heading" key={index}>{first.replace(/^SLIDE\s+\d+:\s*/, '')}</h3>;
    }
    return (
      <div className="results-content-block" key={index}>
        {lines.map((line, li) => {
          const bullet = /^[—\-•]\s+/.test(line);
          return bullet
            ? <div className="results-content-bullet" key={li}>{line.replace(/^[—\-•]\s+/, '')}</div>
            : <p key={li}>{line}</p>;
        })}
      </div>
    );
  });
}

// ── Claim Item (Phase 4: Why This? evidence popover) ─────────────────────────
function ClaimItem({ claim }) {
  const [showEvidence, setShowEvidence] = useState(false);
  const isSupported = claim.status === 'supported';
  return (
    <div className={`claim-item claim-item--${isSupported ? 'supported' : 'unsupported'}`}>
      <div className="claim-item-header">
        <div className="claim-status-badge">
          {isSupported ? '✓ Supported' : '⚠ Unsupported'}
        </div>
        {isSupported && claim.evidence && (
          <button
            type="button"
            className="claim-why-btn"
            onClick={() => setShowEvidence(v => !v)}
            aria-expanded={showEvidence}
            title="Show source evidence"
          >
            {showEvidence ? 'Hide source' : 'Why this?'}
          </button>
        )}
      </div>
      <p className="claim-text">{claim.claim}</p>
      {isSupported && claim.evidence && showEvidence && (
        <div className="claim-evidence-popover">
          <span className="claim-evidence-label">Source evidence:</span>
          <blockquote className="claim-evidence-quote">{claim.evidence}</blockquote>
        </div>
      )}
      {!isSupported && (
        <p className="claim-evidence claim-evidence--missing">
          {claim.reason || 'No matching evidence found in source.'}
        </p>
      )}
    </div>
  );
}

// ── Verification Panel ────────────────────────────────────────────────────────
function VerificationPanel({ verification }) {
  const [expanded, setExpanded] = useState(false);

  if (!verification) {
    return (
      <div className="verification-panel verification-panel--unknown">
        <span className="verif-icon">◌</span>
        <span>Verification not available</span>
      </div>
    );
  }

  if (verification.error && !verification.claims?.length) {
    return (
      <div className="verification-panel verification-panel--unknown">
        <span className="verif-icon">◌</span>
        <span>{verification.error}</span>
      </div>
    );
  }

  const unsupported = verification.unsupported_count ?? 0;
  const claims      = verification.claims ?? [];

  if (unsupported === 0 && claims.length > 0) {
    return (
      <div className="verification-panel verification-panel--ok">
        <span className="verif-icon">✓</span>
        <span>Source grounded — {claims.length} claims verified</span>
        {claims.length > 0 && (
          <button
            type="button"
            className="verif-toggle"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
          >
            {expanded ? 'Hide details' : 'View claims'}
          </button>
        )}
        {expanded && (
          <div className="claim-list">
            {claims.map((c, i) => (
              <ClaimItem key={i} claim={c} />
            ))}
          </div>
        )}
      </div>
    );
  }

  if (unsupported > 0) {
    return (
      <div className="verification-panel verification-panel--warn">
        <span className="verif-icon">⚠</span>
        <span>
          {unsupported} unsupported {unsupported === 1 ? 'claim' : 'claims'} detected
        </span>
        <button
          type="button"
          className="verif-toggle"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
        >
          {expanded ? 'Hide claims' : 'Review claims'}
        </button>
        {expanded && (
          <div className="claim-list">
            {claims.map((c, i) => (
              <ClaimItem key={i} claim={c} />
            ))}
          </div>
        )}
      </div>
    );
  }

  // No claims extracted
  return (
    <div className="verification-panel verification-panel--unknown">
      <span className="verif-icon">◌</span>
      <span>No specific claims were extracted for verification</span>
    </div>
  );
}

// ── Consistency Banner (Phase 3) ──────────────────────────────────────────────
function ConsistencyBanner({ consistency }) {
  const [expanded, setExpanded] = useState(false);
  if (!consistency) return null;

  const score         = consistency.consistency_score ?? 100;
  const contradictions = consistency.contradictions ?? [];
  if (contradictions.length === 0) return null;

  const severityColor = { high: '#FC5C65', medium: '#F7B731', low: '#45AAF2' };

  return (
    <div className="consistency-banner consistency-banner--warn">
      <div className="consistency-banner-header">
        <span className="consistency-icon">⚡</span>
        <span>
          <strong>{contradictions.length} cross-format {contradictions.length === 1 ? 'contradiction' : 'contradictions'} detected</strong>
          {' '}&mdash; Consistency score: <strong>{score}/100</strong>
        </span>
        <button
          type="button"
          className="verif-toggle"
          onClick={() => setExpanded(v => !v)}
          aria-expanded={expanded}
        >
          {expanded ? 'Hide' : 'Review'}
        </button>
      </div>
      {expanded && (
        <div className="consistency-detail-list">
          {contradictions.map((c, i) => (
            <div key={i} className="consistency-item">
              <div className="consistency-item-meta">
                <span
                  className="consistency-severity-badge"
                  style={{ color: severityColor[c.severity] || '#7F8C8D' }}
                >
                  {c.severity?.toUpperCase()}
                </span>
                <span className="consistency-formats-label">
                  {(c.formats || []).join(' vs ')}
                </span>
              </div>
              <div className="consistency-claims-row">
                <div className="consistency-claim-block">
                  <span className="consistency-claim-fmt">{(c.formats || [])[0]}</span>
                  <p className="consistency-claim-text">"{c.claim_a}"</p>
                </div>
                <span className="consistency-vs">≠</span>
                <div className="consistency-claim-block">
                  <span className="consistency-claim-fmt">{(c.formats || [])[1]}</span>
                  <p className="consistency-claim-text">"{c.claim_b}"</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Infographic PNG export (browser-side via html-to-image if available) ──────
async function exportInfographicPng(element) {
  try {
    // Dynamically import html-to-image only if needed
    const { toPng } = await import('html-to-image');
    const dataUrl = await toPng(element, { cacheBust: true });
    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = 'omniformat-infographic.png';
    a.click();
  } catch {
    // Fallback: open card in a new window for manual save
    alert('PNG export not available. Use browser Print → Save as PDF/Image instead.');
  }
}

// ── Main ResultsWorkspace ─────────────────────────────────────────────────────
// results shape: { fmt_key: { status: 'success'|'error', content, verification, infographic_data?, error } }
export default function ResultsWorkspace({
  results,
  consistency,
  sourceChanged,
  onRegenerate,
  regenLoading,
  onCopy,
  copied,
  onDownloadPptx,
  onDownloadPdf,
}) {
  // Map from key → label
  const formatLabelMap = Object.fromEntries(OUTPUT_OPTS.map(({ key, label }) => [key, label]));

  // Build tab list only from formats that were requested (exist in results)
  const tabs = OUTPUT_OPTS.filter(({ key }) => key in results);

  const [activeTab, setActiveTab] = useState(tabs.length > 0 ? tabs[0].key : '');
  const [rawOpen,   setRawOpen]   = useState(false);

  // Build a set of formats involved in contradictions for tab badge display
  const contradictedFormats = new Set(
    (consistency?.contradictions || []).flatMap(c => c.formats || [])
  );

  if (tabs.length === 0) {
    return (
      <div className="results-workspace" style={{ padding: '24px 18px', color: 'var(--text-3)' }}>
        No outputs were returned.
      </div>
    );
  }

  const validTab = tabs.some(({ key }) => key === activeTab) ? activeTab : tabs[0].key;
  const currentResult = results[validTab] ?? {};
  const isSuccess     = currentResult.status === 'success';
  const isError       = currentResult.status === 'error';
  const content       = isSuccess ? cleanOutput(currentResult.content ?? '') : '';
  const isCopied      = copied === validTab;

  const isPptxTab = validTab === 'presentation';
  const isPdfTab  = validTab === 'advisory' || validTab === 'executive_summary';
  const isInfographic = validTab === 'infographic';

  const switchTab = (key) => { setActiveTab(key); setRawOpen(false); };

  const handleExportPng = useCallback((element) => {
    exportInfographicPng(element);
  }, []);

  return (
    <div className="results-workspace" role="region" aria-label="Generated outputs">

      {/* Source Changed / Version Banner */}
      <VersionBanner
        sourceChanged={sourceChanged}
        results={results}
        onRegenerate={onRegenerate}
        regenLoading={regenLoading}
      />

      {/* Cross-Format Consistency Banner */}
      <ConsistencyBanner consistency={consistency} />

      {/* Tab bar */}
      <div className="results-tabs" role="tablist" aria-label="Output formats">
        {tabs.map(({ key, label }) => {
          const r = results[key];
          const hasError = r?.status === 'error';
          const hasConflict = contradictedFormats.has(key);
          return (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={key === validTab}
              aria-controls={`tabpanel-${key}`}
              id={`tab-${key}`}
              className={[
                'results-tab',
                key === validTab ? 'results-tab--active' : '',
                hasError ? 'results-tab--error' : '',
                hasConflict ? 'results-tab--conflict' : '',
              ].join(' ').trim()}
              onClick={() => switchTab(key)}
            >
              {hasError    && <span className="tab-error-dot"    aria-label="error" />}
              {hasConflict && <span className="tab-conflict-dot" aria-label="contradiction" />}
              {label}
            </button>
          );
        })}
      </div>

      {/* Content panel */}
      <div
        id={`tabpanel-${validTab}`}
        role="tabpanel"
        aria-labelledby={`tab-${validTab}`}
        className="results-panel"
      >
        <div className="results-panel-header">
          <h2 className="results-panel-title">{formatLabelMap[validTab] ?? validTab}</h2>
          <div className="results-panel-actions">
            {isSuccess && (
              <>
                {isPptxTab && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm btn--download"
                    onClick={() => onDownloadPptx(content)}
                    aria-label="Download as PowerPoint"
                  >
                    <DownloadIcon /> PPTX
                  </button>
                )}
                {isPdfTab && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm btn--download"
                    onClick={() => onDownloadPdf(content, formatLabelMap[validTab])}
                    aria-label="Download as PDF"
                  >
                    <DownloadIcon /> PDF
                  </button>
                )}
                {isInfographic && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm btn--download"
                    onClick={() => {
                      const el = document.querySelector('.infographic-card');
                      if (el) handleExportPng(el);
                    }}
                    aria-label="Export infographic as PNG"
                  >
                    <DownloadIcon /> PNG
                  </button>
                )}
                {!isInfographic && (
                  <button
                    type="button"
                    className={`btn btn-ghost btn-sm${isCopied ? ' btn--copied' : ''}`}
                    onClick={() => onCopy(content, validTab)}
                    aria-label={`Copy ${formatLabelMap[validTab]} to clipboard`}
                  >
                    {isCopied ? <><CheckIcon /> Copied</> : <><CopyIcon /> Copy</>}
                  </button>
                )}
              </>
            )}
          </div>
        </div>

        {/* Error state */}
        {isError && (
          <div className="results-error-state">
            <span className="results-error-icon">⚠</span>
            <div>
              <strong>This format could not be generated.</strong>
              <p>{currentResult.error || 'An unknown error occurred.'}</p>
            </div>
          </div>
        )}

        {/* Content */}
        {isSuccess && (
          <>
            <div className="results-content">
              {isInfographic
                ? <InfographicCard content={currentResult.content} onExportPng={handleExportPng} />
                : <FormattedOutput content={content} />
              }
            </div>

            {/* Verification panel (not for infographic) */}
            {!isInfographic && (
              <VerificationPanel verification={currentResult.verification} />
            )}
          </>
        )}

        {/* Raw JSON toggle */}
        <details
          className="results-raw"
          open={rawOpen}
          onToggle={(e) => setRawOpen(e.target.open)}
        >
          <summary className="results-raw-toggle">
            {rawOpen ? 'Hide' : 'Show'} raw response
          </summary>
          {rawOpen && (
            <pre className="results-raw-pre">
              {JSON.stringify(currentResult, null, 2)}
            </pre>
          )}
        </details>
      </div>
    </div>
  );
}
