import { useState, useEffect, useRef } from 'react';

import AppShell           from './components/AppShell';
import SourceInput        from './components/SourceInput';
import OutputSelector     from './components/OutputSelector';
import GenerationControls from './components/GenerationControls';
import ResultsWorkspace   from './components/ResultsWorkspace';
import Toast              from './components/Toast';
import AnimatedContent    from './components/AnimatedContent';
import HistoryDrawer      from './components/HistoryDrawer';
import { apiFetch, apiJson } from './lib/api';
import { useAuth } from './context/AuthContext';
import { cx } from './lib/ui';
import { saveBlob } from './lib/download';
import { OUTPUT_OPTS, TONES, AUDIENCES } from './lib/formats';

/** Titled panel wrapper used by the workspace form. */
function Section({ id, title, helper, children }) {
  return (
    <section className="rounded-xl border border-line bg-surface shadow-panel" aria-labelledby={id}>
      <div className="border-b border-line px-5 py-3.5">
        <h2 id={id} className="text-sm font-semibold text-ink">{title}</h2>
        {helper && <p className="mt-0.5 text-xs text-ink-muted">{helper}</p>}
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}

const LOADING_STEP_INTERVAL_MS = 2500;

export default function App() {
  const { user, signOutUser } = useAuth();

  // ── Source state ──────────────────────────────────────────────
  const [sourceType, setSourceType] = useState('text'); // 'text' | 'file' | 'url'
  const [text,       setText]       = useState('');
  const [file,       setFile]       = useState(null);
  const [url,        setUrl]        = useState('');

  // ── Output / controls state ───────────────────────────────────
  const [outputs, setOutputs] = useState({
    advisory:          true,
    executive_summary: true,
    linkedin:          false,
    x_thread:          false,
    presentation:      false,
    infographic:       false,
  });
  const [tone,     setTone]     = useState('Professional');
  const [audience, setAudience] = useState('Leadership / Execs');

  // ── Generation state ──────────────────────────────────────────
  const [loading,     setLoading]     = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [engineErr,   setEngineErr]   = useState('');
  const [result,      setResult]      = useState(null);   // { run_id, results, consistency, ground_truth }

  // ── Source versioning ─────────────────────────────────────────
  const [loadedRunSource, setLoadedRunSource] = useState(null); // source text of loaded history run
  const [sourceChanged,   setSourceChanged]   = useState(false);
  const [regenLoading,    setRegenLoading]    = useState(false);

  // ── History ───────────────────────────────────────────────────
  const [history,      setHistory]      = useState([]);
  const [historyError, setHistoryError] = useState('');
  const [showHistory,  setShowHistory]  = useState(false);

  // ── Toast ─────────────────────────────────────────────────────
  const [copied,       setCopied]       = useState('');
  const [toastVisible, setToastVisible] = useState('');

  // ── Backend config (per-format LLM routing) ──────────────────
  const [formatRouting, setFormatRouting] = useState({});

  const stepTimerRef = useRef(null);

  // ── Fetch backend routing once (unauthenticated /health) ──────
  useEffect(() => {
    fetch(`${import.meta.env.VITE_GEN_AI_API_URL || 'http://localhost:8000'}/health`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d?.format_routing && setFormatRouting(d.format_routing))
      .catch(() => {});
  }, []);

  // ── Loading step cycling ──────────────────────────────────────
  useEffect(() => {
    if (loading) {
      stepTimerRef.current = setInterval(() => {
        setLoadingStep((s) => s + 1);
      }, LOADING_STEP_INTERVAL_MS);
    } else {
      clearInterval(stepTimerRef.current);
    }
    return () => clearInterval(stepTimerRef.current);
  }, [loading]);

  // ── History handlers ──────────────────────────────────────────
  const openHistory = async () => {
    setHistoryError('');
    try {
      const data = await apiJson('/history');
      setHistory(data.history || []);
    } catch (err) {
      setHistoryError(err.message || 'Unable to load history.');
    }
    setShowHistory(true);
  };

  const selectHistory = async (item) => {
    // Fetch full run (with outputs) — do NOT regenerate
    setShowHistory(false);
    setEngineErr('');
    setSourceChanged(false);
    try {
      const data = await apiJson(`/history/${encodeURIComponent(item.run_id)}`);
      setResult({
        run_id:        data.run_id,
        results:       data.results || {},
        consistency:   data.consistency || null,
        ground_truth:  data.ground_truth || null,
        integrity:     data.integrity || null,
      });
      if (data.parameters) {
        setTone(data.parameters.tone || 'Professional');
        setAudience(data.parameters.audience || 'Leadership / Execs');
      }
      if (data.source?.content) {
        const src = data.source.content.slice(0, 5000);
        setText(src);
        setSourceType('text');
        setLoadedRunSource(src); // remember original source for version comparison
      }
    } catch (err) {
      setEngineErr(err.message || 'Could not load history run.');
    }
  };

  const newWorkspace = () => {
    setResult(null);
    setText('');
    setFile(null);
    setUrl('');
    setEngineErr('');
    setShowHistory(false);
    setLoadedRunSource(null);
    setSourceChanged(false);
  };

  // ── Source change detection ────────────────────────────────────
  const handleTextChange = (newText) => {
    setText(newText);
    if (loadedRunSource !== null) {
      setSourceChanged(newText.trim() !== loadedRunSource.trim());
    }
  };

  // ── Surgical regeneration ─────────────────────────────────────
  const handleRegenerate = async (formats) => {
    if (!formats.length) return;
    setRegenLoading(true);
    setEngineErr('');
    try {
      const data = await apiJson('/regenerate', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          run_id:   result?.run_id || '',
          source:   text,
          formats:  formats,
          tone,
          audience,
        }),
      });
      setResult({
        run_id:       data.run_id,
        results:      data.results || {},
        consistency:  data.consistency || null,
        ground_truth: data.ground_truth || null,
        integrity:    data.integrity || null,
      });
      setLoadedRunSource(text);
      setSourceChanged(false);
    } catch (err) {
      setEngineErr(err.message);
    } finally {
      setRegenLoading(false);
    }
  };

  // ── Integrity verification ───────────────────────────────────
  const handleVerify = async (formatKey, content) => {
    if (!result?.run_id) throw new Error('No run to verify against.');
    return apiJson('/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: result.run_id, format_name: formatKey, content }),
    });
  };

  // ── Transform handler ─────────────────────────────────────────
  const transform = async (e) => {
    e.preventDefault();

    const selected = Object.keys(outputs).filter((k) => outputs[k]);
    if (!selected.length) {
      setEngineErr('Select at least one output format.');
      return;
    }

    const hasSource =
      (sourceType === 'text'  && text.trim()) ||
      (sourceType === 'file'  && file) ||
      (sourceType === 'url'   && url.trim());

    if (!hasSource) {
      setEngineErr('Add source content — paste text, upload a file, or enter a URL.');
      return;
    }

    setLoadingStep(0);
    setLoading(true);
    setEngineErr('');
    setResult(null);

    const fd = new FormData();
    fd.append('formats',  JSON.stringify(selected));
    fd.append('tone',     tone);
    fd.append('audience', audience);

    if (sourceType === 'text') {
      fd.append('text', text);
    } else if (sourceType === 'file' && file) {
      fd.append('file', file);
    } else if (sourceType === 'url') {
      fd.append('url', url.trim());
    }

    try {
      const res = await apiFetch('/transform', {
        method: 'POST',
        body:   fd,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Server error (${res.status}).`);
      }

      const data = await res.json();
      setResult({
        run_id:       data.run_id,
        results:      data.results,
        consistency:  data.consistency || null,
        ground_truth: data.ground_truth || null,
        integrity:    data.integrity || null,
      });
      setLoadedRunSource(null);
      setSourceChanged(false);
    } catch (err) {
      setEngineErr(err.message);
    } finally {
      setLoading(false);
    }
  };

  const setAllOutputs = (val) => {
    const newOutputs = {};
    OUTPUT_OPTS.forEach(({ key }) => { newOutputs[key] = val; });
    setOutputs(newOutputs);
  };

  // ── Copy ──────────────────────────────────────────────────────
  const handleCopy = (content, key) => {
    navigator.clipboard.writeText(content).then(() => {
      setCopied(key);
      setToastVisible('Copied to clipboard');
      setTimeout(() => { setCopied(''); setToastVisible(''); }, 1800);
    });
  };

  // ── Download PPTX ─────────────────────────────────────────────
  const handleDownloadPptx = async (content) => {
    try {
      const res = await apiFetch('/export/pptx', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, title: 'OmniFormat Presentation' }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'PPTX generation failed.');
      }
      const blob = await res.blob();
      if (blob.size < 1000) throw new Error('PPTX came back empty — check the backend logs.');
      saveBlob(blob, 'omniformat-presentation.pptx');
      setToastVisible('PPTX downloaded');
      setTimeout(() => setToastVisible(''), 2000);
    } catch (err) {
      setEngineErr(err.message);
    }
  };

  // ── Download PDF ──────────────────────────────────────────────
  const handleDownloadPdf = async (content, formatLabel) => {
    try {
      const res = await apiFetch('/export/pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, format_name: formatLabel }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'PDF generation failed.');
      }
      const blob = await res.blob();
      if (blob.size < 500) throw new Error('PDF came back empty — check the backend logs.');
      saveBlob(blob, `omniformat-${formatLabel.toLowerCase().replace(/\s+/g, '-')}.pdf`);
      setToastVisible('PDF downloaded');
      setTimeout(() => setToastVisible(''), 2000);
    } catch (err) {
      setEngineErr(err.message);
    }
  };

  const hasSource =
    (sourceType === 'text' && text.trim()) ||
    (sourceType === 'file' && file) ||
    (sourceType === 'url'  && url.trim());

  const canGenerate = !!hasSource && Object.values(outputs).some(Boolean);
  const step = loading || result ? 2 : canGenerate ? 2 : hasSource ? 1 : 0;

  // ── Render ────────────────────────────────────────────────────
  return (
    <AppShell
      onHistory={openHistory}
      onNewWorkspace={newWorkspace}
      user={user}
      onSignOut={signOutUser}
    >
      <HistoryDrawer
        isOpen={showHistory}
        onClose={() => setShowHistory(false)}
        history={history}
        error={historyError}
        onSelect={selectHistory}
      />

      <div className="mx-auto w-full max-w-5xl overflow-x-hidden px-5 pb-24 pt-8 sm:px-8">
        {/* Header */}
        <AnimatedContent>
          <header className="mb-8">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent">
              OmniFormat AI · Workspace
            </p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">
              Content Transformation Engine
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-muted">
              Turn one source document into an advisory, executive summary, social posts, a deck
              and an infographic — generated in parallel, every claim checked against the source.
            </p>

            <ol className="mt-6 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs">
              {[
                ['01', 'Source material', step >= 0],
                ['02', 'Select formats', step >= 1],
                ['03', 'Generate', step >= 2],
              ].map(([n, label, done], i) => (
                <li key={n} className="flex items-center gap-3">
                  {i > 0 && <span className="hidden h-px w-6 bg-line sm:block" aria-hidden="true" />}
                  <span className={cx('flex items-center gap-2 whitespace-nowrap', done ? 'text-ink' : 'text-ink-subtle')}>
                    <span
                      className={cx(
                        'grid h-5 w-5 place-items-center rounded-full border text-[10px] font-semibold',
                        done ? 'border-accent bg-accent-soft text-accent' : 'border-line text-ink-subtle'
                      )}
                    >
                      {n}
                    </span>
                    {label}
                  </span>
                </li>
              ))}
            </ol>
          </header>
        </AnimatedContent>

        <form className="space-y-5" onSubmit={transform} noValidate>
          <AnimatedContent>
            <Section
              id="lbl-source"
              title="Source material"
              helper="Paste text, upload a PDF / DOCX / TXT, or enter a URL."
            >
              <SourceInput
                sourceType={sourceType}
                onSourceTypeChange={setSourceType}
                text={text}
                onTextChange={sourceType === 'text' ? handleTextChange : setText}
                file={file}
                onFileChange={setFile}
                url={url}
                onUrlChange={setUrl}
              />
            </Section>
          </AnimatedContent>

          <AnimatedContent>
            <Section
              id="lbl-formats"
              title="Output formats"
              helper="Each format is a separate specialised agent — they run concurrently."
            >
              <OutputSelector
                outputs={outputs}
                onToggle={(key) => setOutputs((o) => ({ ...o, [key]: !o[key] }))}
                onToggleAll={setAllOutputs}
                options={OUTPUT_OPTS}
                routing={formatRouting}
              />
            </Section>
          </AnimatedContent>

          <GenerationControls
            tone={tone}           onToneChange={setTone}
            audience={audience}   onAudienceChange={setAudience}
            tones={TONES}         audiences={AUDIENCES}
            loading={loading}
            loadingStep={loadingStep}
            error={engineErr}
            canGenerate={canGenerate}
          />
        </form>

        {result && (
          <section className="mt-8" aria-labelledby="lbl-results">
            <h2 id="lbl-results" className="mb-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-subtle">
              Results
            </h2>
            <ResultsWorkspace
              runId={result.run_id}
              results={result.results}
              consistency={result.consistency}
              integrity={result.integrity}
              sourceChanged={sourceChanged}
              onRegenerate={handleRegenerate}
              regenLoading={regenLoading}
              onCopy={handleCopy}
              copied={copied}
              onVerify={handleVerify}
              onDownloadPptx={handleDownloadPptx}
              onDownloadPdf={handleDownloadPdf}
            />
          </section>
        )}
      </div>

      <Toast message={toastVisible} visible={!!toastVisible} />
    </AppShell>
  );
}
