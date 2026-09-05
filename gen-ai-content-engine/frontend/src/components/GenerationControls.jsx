function SelectArrow() {
  return (
    <svg width="10" height="6" viewBox="0 0 10 6" fill="none" aria-hidden="true">
      <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const LOADING_STEPS = [
  'Normalizing source…',
  'Running agents concurrently…',
  'Verifying claims against source…',
  'Finalizing outputs…',
];

export default function GenerationControls({
  tone, onToneChange,
  audience, onAudienceChange,
  tones, audiences,
  loading, loadingStep,
  error, canGenerate,
}) {
  const stepLabel = LOADING_STEPS[loadingStep % LOADING_STEPS.length];

  return (
    <div className="gen-controls">
      {/* Tone + Audience */}
      <div className="gen-row">
        <div className="form-field">
          <label className="form-label" htmlFor="select-tone">Tone</label>
          <div className="select-wrap">
            <select id="select-tone" className="form-select" value={tone} onChange={(e) => onToneChange(e.target.value)}>
              {tones.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <span className="select-arrow"><SelectArrow /></span>
          </div>
        </div>

        <div className="form-field">
          <label className="form-label" htmlFor="select-audience">Target audience</label>
          <div className="select-wrap">
            <select id="select-audience" className="form-select" value={audience} onChange={(e) => onAudienceChange(e.target.value)}>
              {audiences.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
            <span className="select-arrow"><SelectArrow /></span>
          </div>
        </div>
      </div>

      {/* Submit */}
      <div className="sticky-action">
        <div className="sticky-action-copy">
          <strong>{loading ? 'Agents running' : 'Ready to generate'}</strong>
          <span>{loading ? stepLabel : 'Each format runs as a separate specialised agent'}</span>
        </div>
        <button
          type="submit"
          className="btn btn-primary btn-full btn-generate"
          disabled={loading || !canGenerate}
          aria-busy={loading}
        >
          {loading ? (
            <><span className="spinner" aria-hidden="true" /><span>{stepLabel}</span></>
          ) : (
            'Generate outputs'
          )}
        </button>
      </div>

      {/* Error */}
      {error && <p className="form-msg form-msg--error" role="alert">{error}</p>}
    </div>
  );
}
