import { useState } from 'react';
import { OUTPUT_OPTS } from '../App';

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

function ClaimItem({ claim }) {
  const isSupported = claim.status === 'supported';
  return (
    <div className={`claim-item claim-item--${isSupported ? 'supported' : 'unsupported'}`}>
      <div className="claim-status-badge">
        {isSupported ? '✓ Supported' : '⚠ Unsupported'}
      </div>
      <p className="claim-text">{claim.claim}</p>
      {isSupported && claim.evidence && (
        <p className="claim-evidence">
          <strong>Evidence:</strong> {claim.evidence}
        </p>
      )}
      {!isSupported && (
        <p className="claim-evidence claim-evidence--missing">
          {claim.reason || 'No matching evidence found in source.'}
        </p>
      )}
    </div>
  );
}

// ── Main ResultsWorkspace ─────────────────────────────────────────────────────
// results shape: { fmt_key: { status: 'success'|'error', content, verification, error } }
export default function ResultsWorkspace({ results, onCopy, copied, onDownloadPptx, onDownloadPdf }) {
  // Map from key → label
  const formatLabelMap = Object.fromEntries(OUTPUT_OPTS.map(({ key, label }) => [key, label]));

  // Build tab list only from formats that were requested (exist in results)
  const tabs = OUTPUT_OPTS.filter(({ key }) => key in results);

  const [activeTab, setActiveTab] = useState(tabs.length > 0 ? tabs[0].key : '');
  const [rawOpen,   setRawOpen]   = useState(false);

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

  const switchTab = (key) => { setActiveTab(key); setRawOpen(false); };

  return (
    <div className="results-workspace" role="region" aria-label="Generated outputs">
      {/* Tab bar */}
      <div className="results-tabs" role="tablist" aria-label="Output formats">
        {tabs.map(({ key, label }) => {
          const r = results[key];
          const hasError = r?.status === 'error';
          return (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={key === validTab}
              aria-controls={`tabpanel-${key}`}
              id={`tab-${key}`}
              className={`results-tab${key === validTab ? ' results-tab--active' : ''}${hasError ? ' results-tab--error' : ''}`}
              onClick={() => switchTab(key)}
            >
              {hasError && <span className="tab-error-dot" aria-label="error" />}
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
                <button
                  type="button"
                  className={`btn btn-ghost btn-sm${isCopied ? ' btn--copied' : ''}`}
                  onClick={() => onCopy(content, validTab)}
                  aria-label={`Copy ${formatLabelMap[validTab]} to clipboard`}
                >
                  {isCopied ? <><CheckIcon /> Copied</> : <><CopyIcon /> Copy</>}
                </button>
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
              <FormattedOutput content={content} />
            </div>

            {/* Verification panel */}
            <VerificationPanel verification={currentResult.verification} />
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
