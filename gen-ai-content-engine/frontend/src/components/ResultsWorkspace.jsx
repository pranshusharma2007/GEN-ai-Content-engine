import { useCallback, useState } from 'react';

import { OUTPUT_OPTS } from '../lib/formats';
import { cx, ui } from '../lib/ui';
import { saveDataUrl } from '../lib/download';
import InfographicCard from './InfographicCard';
import VersionBanner from './VersionBanner';

const PROVIDER_LABEL = { groq: 'Groq', gemini: 'Gemini', openai: 'GPT', anthropic: 'Claude', ollama: 'Ollama' };

/* ── Icons ───────────────────────────────────────────────────────────────── */
const CopyIcon = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
    <rect x="4.5" y="4.5" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.2" />
    <path d="M4.5 4.5V3a1 1 0 011-1h5a1 1 0 011 1v5a1 1 0 01-1 1H9" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
  </svg>
);
const CheckIcon = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
    <path d="M2 6.5L5 9.5L11 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
const DownloadIcon = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
    <path d="M6.5 1v8M3.5 6.5l3 3 3-3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M1.5 11.5h10" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
  </svg>
);

/* ── Text cleaners ───────────────────────────────────────────────────────── */
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
  return (
    <div className="space-y-4 text-sm leading-relaxed text-ink-muted">
      {cleanOutput(content).split(/\n{2,}/).map((block, index) => {
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
          return (
            <h4 key={index} className="text-xs font-semibold uppercase tracking-wide text-ink">
              {first.replace(/^SLIDE\s+\d+:\s*/, '')}
            </h4>
          );
        }
        return (
          <div key={index} className="space-y-1.5">
            {lines.map((line, li) => {
              const bullet = /^[—\-•]\s+/.test(line);
              return bullet ? (
                <div key={li} className="flex gap-2">
                  <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-accent" />
                  <span>{line.replace(/^[—\-•]\s+/, '')}</span>
                </div>
              ) : (
                <p key={li}>{line}</p>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}

/* ── Claim item with evidence popover ────────────────────────────────────── */
function ClaimItem({ claim }) {
  const [open, setOpen] = useState(false);
  const supported = claim.status === 'supported';
  return (
    <div className={cx('rounded-lg border p-2.5', supported ? 'border-line bg-surface-2' : 'border-warning/35 bg-warning-soft')}>
      <div className="flex items-center justify-between gap-2">
        <span className={cx('inline-flex items-center gap-1.5 text-[11px] font-semibold', supported ? 'text-success' : 'text-warning')}>
          {supported ? <CheckIcon /> : '⚠'} {supported ? 'Supported' : 'Unsupported'}
        </span>
        {supported && claim.evidence && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="text-[11px] font-medium text-ink-subtle hover:text-ink"
          >
            {open ? 'Hide source' : 'Why this?'}
          </button>
        )}
      </div>
      <p className="mt-1.5 text-xs text-ink">{claim.claim}</p>
      {supported && claim.evidence && open && (
        <blockquote className="mt-2 border-l-2 border-accent/60 bg-inset px-2.5 py-1.5 text-[11px] italic text-ink-muted">
          {claim.evidence}
        </blockquote>
      )}
      {!supported && (
        <p className="mt-1.5 text-[11px] text-warning/90">
          {claim.reason || 'No matching evidence found in source.'}
        </p>
      )}
    </div>
  );
}

/* ── Verification panel ──────────────────────────────────────────────────── */
function VerificationPanel({ verification }) {
  const [expanded, setExpanded] = useState(false);

  if (!verification || (verification.error && !verification.claims?.length)) {
    return (
      <div className="mt-4 flex items-center gap-2 rounded-lg border border-line bg-surface-2 px-3 py-2 text-xs text-ink-subtle">
        <span>◌</span>
        <span>{verification?.error || 'Verification not available'}</span>
      </div>
    );
  }

  const unsupported = verification.unsupported_count ?? 0;
  const claims = verification.claims ?? [];
  const ok = unsupported === 0 && claims.length > 0;
  const warn = unsupported > 0;

  const tone = warn
    ? 'border-warning/35 bg-warning-soft text-warning'
    : ok
      ? 'border-success/30 bg-success-soft text-success'
      : 'border-line bg-surface-2 text-ink-subtle';

  return (
    <div className={cx('mt-4 rounded-lg border px-3 py-2.5', tone)}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <span className="text-sm">{warn ? '⚠' : ok ? '✓' : '◌'}</span>
        <span className="font-medium">
          {warn
            ? `${unsupported} unsupported ${unsupported === 1 ? 'claim' : 'claims'} — flagged, not removed`
            : ok
              ? `Source-grounded — ${claims.length} ${claims.length === 1 ? 'claim' : 'claims'} traced to the document`
              : 'No specific claims were extracted for verification'}
        </span>
        {claims.length > 0 && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            className="ml-auto font-medium underline-offset-2 hover:underline"
          >
            {expanded ? 'Hide claims' : warn ? 'Review claims' : 'View claims'}
          </button>
        )}
      </div>
      {expanded && (
        <div className="mt-2.5 space-y-1.5">
          {claims.map((c, i) => <ClaimItem key={i} claim={c} />)}
        </div>
      )}
    </div>
  );
}

/* ── Cross-format consistency banner ─────────────────────────────────────── */
function ConsistencyBanner({ consistency }) {
  const [expanded, setExpanded] = useState(false);
  if (!consistency) return null;

  const score = consistency.consistency_score ?? 100;
  const contradictions = consistency.contradictions ?? [];
  const clean = contradictions.length === 0;

  if (clean) {
    return (
      <div className="mb-3 flex items-center gap-2 rounded-lg border border-success/25 bg-success-soft px-3 py-2 text-xs text-success">
        <span className="text-sm">✓</span>
        <span className="font-medium">All formats consistent — no cross-format contradictions ({score}/100)</span>
      </div>
    );
  }

  const sevColor = { high: 'text-danger', medium: 'text-warning', low: 'text-info' };

  return (
    <div className="mb-3 rounded-lg border border-warning/35 bg-warning-soft px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-warning">
        <span className="text-sm">⚡</span>
        <span className="font-medium">
          {contradictions.length} cross-format {contradictions.length === 1 ? 'contradiction' : 'contradictions'} — consistency {score}/100
        </span>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="ml-auto font-medium underline-offset-2 hover:underline"
        >
          {expanded ? 'Hide' : 'Review'}
        </button>
      </div>
      {expanded && (
        <div className="mt-2.5 space-y-2">
          {contradictions.map((c, i) => (
            <div key={i} className="rounded-md border border-line bg-surface-2 p-2.5">
              <div className="flex items-center gap-2 text-[10px] font-semibold uppercase">
                <span className={sevColor[c.severity] || 'text-ink-subtle'}>{c.severity}</span>
                <span className="text-ink-subtle">{(c.formats || []).join(' vs ')}</span>
              </div>
              <div className="mt-1.5 grid gap-1.5 text-xs text-ink sm:grid-cols-[1fr_auto_1fr] sm:items-center">
                <p className="rounded bg-inset px-2 py-1">“{c.claim_a}”</p>
                <span className="text-center text-ink-subtle">≠</span>
                <p className="rounded bg-inset px-2 py-1">“{c.claim_b}”</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Tamper-evident integrity panel ─────────────────────────────────────── */
function short(hash, n = 16) {
  return hash ? hash.slice(0, n) : '';
}

function IntegrityPanel({ formatKey, storedHash, algo = 'sha256', rawContent, onVerify }) {
  const [tamperOpen, setTamperOpen] = useState(false);
  const [draft, setDraft] = useState(rawContent ?? '');
  const [state, setState] = useState({ status: 'idle' }); // idle | checking | done | error

  if (!storedHash) return null;

  const run = async () => {
    setState({ status: 'checking' });
    try {
      const res = await onVerify(formatKey, tamperOpen ? draft : rawContent);
      setState({ status: 'done', res });
    } catch (e) {
      setState({ status: 'error', message: e.message });
    }
  };

  const res = state.res;
  const tone =
    state.status === 'done'
      ? res.verified
        ? 'border-success/30 bg-success-soft'
        : 'border-danger/40 bg-danger-soft'
      : 'border-line bg-surface-2';

  return (
    <div className={cx('mt-3 rounded-lg border px-3 py-2.5', tone)}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-xs">
        <span className="text-ink-subtle">🔒</span>
        <span className="font-medium text-ink-muted">{algo.toUpperCase()} fingerprint</span>
        <code className="rounded bg-inset px-1.5 py-0.5 font-mono text-[11px] text-ink-muted">
          {short(storedHash)}…
        </code>
        <div className="ml-auto flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setTamperOpen((v) => !v)}
            className={cx('rounded-md px-2 py-1 text-[11px] font-medium', tamperOpen ? 'bg-elevated text-ink' : 'text-ink-subtle hover:text-ink')}
          >
            Tamper test
          </button>
          <button
            type="button"
            onClick={run}
            disabled={state.status === 'checking'}
            className={cx(ui.btnBase, ui.btnGhost, ui.sizeSm)}
          >
            {state.status === 'checking' ? 'Verifying…' : 'Verify integrity'}
          </button>
        </div>
      </div>

      {tamperOpen && (
        <div className="mt-2.5">
          <p className="mb-1.5 text-[11px] text-ink-subtle">
            Edit any character below and re-verify — the fingerprint will no longer match.
          </p>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={5}
            className="w-full resize-y rounded-md border border-line-strong bg-inset p-2.5 font-mono text-[11px] leading-relaxed text-ink outline-none focus:border-accent"
          />
        </div>
      )}

      {state.status === 'done' && (
        <div className="mt-2 text-xs">
          <p className={cx('font-medium', res.verified ? 'text-success' : 'text-danger')}>
            {res.verified
              ? '✓ Matches the fingerprint recorded at generation — content is intact.'
              : '✗ Does NOT match — this content has been altered since it was generated.'}
          </p>
          {!res.verified && (
            <div className="mt-1.5 space-y-0.5 font-mono text-[10px] text-ink-subtle">
              <div>recorded&nbsp;: {short(res.stored_hash, 32)}…</div>
              <div>computed&nbsp;: {short(res.computed_hash, 32)}…</div>
            </div>
          )}
        </div>
      )}
      {state.status === 'error' && (
        <p className="mt-2 text-xs text-danger">Verification failed: {state.message}</p>
      )}
    </div>
  );
}

async function exportInfographicPng(element) {
  try {
    const { toPng } = await import('html-to-image');
    const dataUrl = await toPng(element, { cacheBust: true, pixelRatio: 2 });
    saveDataUrl(dataUrl, 'omniformat-infographic.png');
  } catch {
    alert('PNG export not available. Use the browser Print → Save as PDF instead.');
  }
}

/* ── Main ────────────────────────────────────────────────────────────────── */
export default function ResultsWorkspace({
  runId,
  results,
  consistency,
  integrity,
  sourceChanged,
  onRegenerate,
  regenLoading,
  onCopy,
  copied,
  onVerify,
  onDownloadPptx,
  onDownloadPdf,
}) {
  const formatLabelMap = Object.fromEntries(OUTPUT_OPTS.map(({ key, label }) => [key, label]));
  const tabs = OUTPUT_OPTS.filter(({ key }) => key in results);

  const [activeTab, setActiveTab] = useState(tabs.length ? tabs[0].key : '');
  const [rawOpen, setRawOpen] = useState(false);

  const contradictedFormats = new Set(
    (consistency?.contradictions || []).flatMap((c) => c.formats || [])
  );

  const handleExportPng = useCallback((element) => { exportInfographicPng(element); }, []);

  if (!tabs.length) {
    return (
      <div className="rounded-xl border border-line bg-surface p-6 text-sm text-ink-subtle">
        No outputs were returned.
      </div>
    );
  }

  const validTab = tabs.some(({ key }) => key === activeTab) ? activeTab : tabs[0].key;
  const currentResult = results[validTab] ?? {};
  const isSuccess = currentResult.status === 'success';
  const isError = currentResult.status === 'error';
  const content = isSuccess ? cleanOutput(currentResult.content ?? '') : '';
  const isCopied = copied === validTab;

  const isPptxTab = validTab === 'presentation';
  const isPdfTab = validTab === 'advisory' || validTab === 'executive_summary';
  const isInfographic = validTab === 'infographic';

  const switchTab = (key) => { setActiveTab(key); setRawOpen(false); };

  return (
    <div className="rounded-xl border border-line bg-surface shadow-panel" role="region" aria-label="Generated outputs">
      <div className="p-4 pb-0">
        <VersionBanner
          sourceChanged={sourceChanged}
          results={results}
          onRegenerate={onRegenerate}
          regenLoading={regenLoading}
        />
        <ConsistencyBanner consistency={consistency} />
        {integrity?.run_hash && (
          <div className="mb-3 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-line bg-surface-2 px-3 py-2 text-xs text-ink-muted">
            <span className="text-ink-subtle">🔒</span>
            <span className="font-medium">Run fingerprint</span>
            <code className="rounded bg-inset px-1.5 py-0.5 font-mono text-[11px]">
              {(integrity.algo || 'sha256').toUpperCase()} {short(integrity.run_hash, 24)}…
            </code>
            <span className="text-ink-subtle">every output below is individually hash-logged</span>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-1.5 border-b border-line px-4 pb-3" role="tablist" aria-label="Output formats">
        {tabs.map(({ key, label }) => {
          const r = results[key];
          const hasError = r?.status === 'error';
          const hasConflict = contradictedFormats.has(key);
          const unsupported = r?.verification?.unsupported_count ?? 0;
          const active = key === validTab;
          return (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => switchTab(key)}
              className={cx(
                'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition',
                active ? 'bg-elevated text-ink' : 'text-ink-muted hover:bg-surface-2 hover:text-ink'
              )}
            >
              {hasError && <span className="h-1.5 w-1.5 rounded-full bg-danger" aria-label="error" />}
              {!hasError && hasConflict && <span className="h-1.5 w-1.5 rounded-full bg-warning" aria-label="contradiction" />}
              {!hasError && !hasConflict && unsupported > 0 && (
                <span className="h-1.5 w-1.5 rounded-full bg-warning" aria-label="unsupported claims" />
              )}
              {!hasError && !hasConflict && unsupported === 0 && r?.status === 'success' && (
                <span className="h-1.5 w-1.5 rounded-full bg-success/70" aria-label="verified" />
              )}
              {label}
            </button>
          );
        })}
      </div>

      {/* Panel */}
      <div id={`tabpanel-${validTab}`} role="tabpanel" className="p-4 sm:p-5">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
            {formatLabelMap[validTab] ?? validTab}
            {currentResult.provider?.served_by && (
              <span className="rounded bg-inset px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-ink-subtle">
                via {PROVIDER_LABEL[currentResult.provider.served_by] || currentResult.provider.served_by}
                {currentResult.provider.assigned &&
                  currentResult.provider.assigned !== currentResult.provider.served_by &&
                  ` (fallback from ${PROVIDER_LABEL[currentResult.provider.assigned] || currentResult.provider.assigned})`}
              </span>
            )}
          </h3>
          <div className="flex items-center gap-1.5">
            {isSuccess && isPptxTab && (
              <button type="button" onClick={() => onDownloadPptx(content)} className={cx(ui.btnBase, ui.btnGhost, ui.sizeSm)}>
                <DownloadIcon /> PPTX
              </button>
            )}
            {isSuccess && isPdfTab && (
              <button type="button" onClick={() => onDownloadPdf(content, formatLabelMap[validTab])} className={cx(ui.btnBase, ui.btnGhost, ui.sizeSm)}>
                <DownloadIcon /> PDF
              </button>
            )}
            {isSuccess && isInfographic && (
              <button
                type="button"
                onClick={() => { const el = document.querySelector('.infographic-card'); if (el) handleExportPng(el); }}
                className={cx(ui.btnBase, ui.btnGhost, ui.sizeSm)}
              >
                <DownloadIcon /> PNG
              </button>
            )}
            {isSuccess && !isInfographic && (
              <button
                type="button"
                onClick={() => onCopy(content, validTab)}
                className={cx(ui.btnBase, ui.sizeSm, isCopied ? 'bg-success-soft text-success' : ui.btnGhost)}
              >
                {isCopied ? <><CheckIcon /> Copied</> : <><CopyIcon /> Copy</>}
              </button>
            )}
          </div>
        </div>

        {isError && (
          <div className="flex gap-3 rounded-lg border border-danger/30 bg-danger-soft p-3 text-sm">
            <span className="text-danger">⚠</span>
            <div>
              <p className="font-medium text-ink">This format could not be generated.</p>
              <p className="mt-0.5 text-xs text-ink-muted">{currentResult.error || 'An unknown error occurred.'}</p>
            </div>
          </div>
        )}

        {isSuccess && (
          <>
            {isInfographic
              ? <InfographicCard content={currentResult.content} onExportPng={handleExportPng} />
              : <FormattedOutput content={content} />}
            {!isInfographic && <VerificationPanel verification={currentResult.verification} />}
            {onVerify && runId && (
              <IntegrityPanel
                key={validTab}
                formatKey={validTab}
                storedHash={currentResult.hash}
                algo={currentResult.hash_algo}
                rawContent={currentResult.content ?? ''}
                onVerify={onVerify}
              />
            )}
          </>
        )}

        <details
          className="mt-4 rounded-lg border border-line bg-surface-2"
          open={rawOpen}
          onToggle={(e) => setRawOpen(e.target.open)}
        >
          <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-ink-subtle hover:text-ink">
            {rawOpen ? 'Hide' : 'Show'} raw response
          </summary>
          {rawOpen && (
            <pre className="max-h-80 overflow-auto border-t border-line p-3 font-mono text-[11px] leading-relaxed text-ink-muted">
              {JSON.stringify(currentResult, null, 2)}
            </pre>
          )}
        </details>
      </div>
    </div>
  );
}
