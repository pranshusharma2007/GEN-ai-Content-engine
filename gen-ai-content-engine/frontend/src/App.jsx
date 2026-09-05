import { useState, useEffect, useRef } from 'react';

import AppShell           from './components/AppShell';
import SourceInput        from './components/SourceInput';
import OutputSelector     from './components/OutputSelector';
import GenerationControls from './components/GenerationControls';
import ResultsWorkspace   from './components/ResultsWorkspace';
import Toast              from './components/Toast';
import AnimatedContent    from './components/AnimatedContent';
import HistoryDrawer      from './components/HistoryDrawer';

import './App.css';

const GW_URL = import.meta.env.VITE_GEN_AI_API_URL || 'http://localhost:8000';

// Format keys must match backend SUPPORTED_FORMATS
export const OUTPUT_OPTS = [
  { key: 'advisory',           label: 'Advisory' },
  { key: 'executive_summary',  label: 'Executive Summary' },
  { key: 'linkedin',           label: 'LinkedIn Post' },
  { key: 'x_thread',           label: 'X / Twitter Thread' },
  { key: 'presentation',       label: 'Presentation' },
  { key: 'infographic',        label: 'Infographic' },
];

const TONES = [
  'Professional',
  'Authoritative & Strategic',
  'Casual & Engaging',
  'Urgent & Action-Oriented',
  'Inspirational',
];

const AUDIENCES = [
  'Leadership / Execs',
  'General Public',
  'Tech / Developers',
  'Sales / Marketing',
  'Stakeholders & Investors',
];

const LOADING_STEP_INTERVAL_MS = 2500;

export default function App() {
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
  const [affectedFormats, setAffectedFormats] = useState([]);
  const [regenLoading,    setRegenLoading]    = useState(false);

  // ── History ───────────────────────────────────────────────────
  const [history,      setHistory]      = useState([]);
  const [historyError, setHistoryError] = useState('');
  const [showHistory,  setShowHistory]  = useState(false);

  // ── Toast ─────────────────────────────────────────────────────
  const [copied,       setCopied]       = useState('');
  const [toastVisible, setToastVisible] = useState('');

  const stepTimerRef = useRef(null);

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
      const res  = await fetch(`${GW_URL}/history`);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Unable to load history (${res.status}).`);
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
    setAffectedFormats([]);
    try {
      const res  = await fetch(`${GW_URL}/history/${encodeURIComponent(item.run_id)}`);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Could not load this run.');
      setResult({
        run_id:        data.run_id,
        results:       data.results || {},
        consistency:   data.consistency || null,
        ground_truth:  data.ground_truth || null,
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
    setAffectedFormats([]);
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
      const res = await fetch(`${GW_URL}/regenerate`, {
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
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Regeneration failed.');
      setResult({
        run_id:       data.run_id,
        results:      data.results || {},
        consistency:  data.consistency || null,
        ground_truth: data.ground_truth || null,
      });
      setLoadedRunSource(text);
      setSourceChanged(false);
      setAffectedFormats([]);
    } catch (err) {
      setEngineErr(err.message);
    } finally {
      setRegenLoading(false);
    }
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
      const res = await fetch(`${GW_URL}/transform`, {
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
      const res = await fetch(`${GW_URL}/export/pptx`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, title: 'OmniFormat Presentation' }),
      });
      if (!res.ok) throw new Error('PPTX generation failed.');
      const blob = await res.blob();
      const href = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = href;
      a.download = 'omniformat-presentation.pptx';
      a.click();
      URL.revokeObjectURL(href);
      setToastVisible('PPTX downloaded');
      setTimeout(() => setToastVisible(''), 2000);
    } catch (err) {
      setEngineErr(err.message);
    }
  };

  // ── Download PDF ──────────────────────────────────────────────
  const handleDownloadPdf = async (content, formatLabel) => {
    try {
      const res = await fetch(`${GW_URL}/export/pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, format_name: formatLabel }),
      });
      if (!res.ok) throw new Error('PDF generation failed.');
      const blob = await res.blob();
      const href = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = href;
      a.download = `omniformat-${formatLabel.toLowerCase().replace(/\s+/g, '-')}.pdf`;
      a.click();
      URL.revokeObjectURL(href);
      setToastVisible('PDF downloaded');
      setTimeout(() => setToastVisible(''), 2000);
    } catch (err) {
      setEngineErr(err.message);
    }
  };

  const canGenerate =
    (
      (sourceType === 'text' && text.trim()) ||
      (sourceType === 'file' && file) ||
      (sourceType === 'url'  && url.trim())
    ) && Object.values(outputs).some(Boolean);

  // ── Render ────────────────────────────────────────────────────
  return (
    <AppShell onHistory={openHistory} onNewWorkspace={newWorkspace}>
      <HistoryDrawer
        isOpen={showHistory}
        onClose={() => setShowHistory(false)}
        history={history}
        error={historyError}
        onSelect={selectHistory}
      />

      <div className="workspace">
        {/* Top bar */}
        <AnimatedContent><header className="workspace-topbar">
          <div className="eyebrow">OMNIFORMAT AI / WORKSPACE</div>
          <h1 className="workspace-title">Content Engine</h1>
          <p className="workspace-subtitle">
            Transform any source into advisory, summaries, social posts, and presentations — simultaneously.
          </p>
          <div className="progress" aria-label="Creation progress">
            <span className="progress-step progress-step--current"><b>01</b> Source material</span>
            <span className="progress-rule" />
            <span className="progress-step"><b>02</b> Select formats</span>
            <span className="progress-rule" />
            <span className="progress-step"><b>03</b> Generate</span>
          </div>
        </header></AnimatedContent>

        {/* Main content */}
        <main className="workspace-main">
          <form className="workspace-form" onSubmit={transform} noValidate>

            {/* Source content */}
            <AnimatedContent><section className="workspace-section" aria-labelledby="lbl-source">
              <div className="section-heading"><div>
                <span className="workspace-section-label" id="lbl-source">Source material</span>
                <p className="section-helper">Paste text, upload a PDF or DOCX, or enter a URL.</p>
              </div></div>
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
            </section></AnimatedContent>

            {/* Output formats */}
            <AnimatedContent><section className="workspace-section" aria-labelledby="lbl-formats">
              <div className="section-heading"><div>
                <span className="workspace-section-label" id="lbl-formats">Output formats</span>
                <p className="section-helper">Agents run in parallel — select any combination.</p>
              </div></div>
              <OutputSelector
                outputs={outputs}
                onToggle={(key) => setOutputs((o) => ({ ...o, [key]: !o[key] }))}
                onToggleAll={setAllOutputs}
                options={OUTPUT_OPTS}
              />
            </section></AnimatedContent>

            {/* Tone, audience, submit */}
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

          {/* Results */}
          {result && (
            <section
              className="workspace-section workspace-section--results"
              aria-labelledby="lbl-results"
            >
              <span className="workspace-section-label" id="lbl-results">Results</span>
              <ResultsWorkspace
                results={result.results}
                consistency={result.consistency}
                sourceChanged={sourceChanged}
                onRegenerate={handleRegenerate}
                regenLoading={regenLoading}
                onCopy={handleCopy}
                copied={copied}
                onDownloadPptx={handleDownloadPptx}
                onDownloadPdf={handleDownloadPdf}
              />
            </section>
          )}
        </main>
      </div>

      <Toast message={toastVisible} visible={!!toastVisible} />
    </AppShell>
  );
}
