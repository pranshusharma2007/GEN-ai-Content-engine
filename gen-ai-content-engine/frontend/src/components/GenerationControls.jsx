import { cx, ui } from '../lib/ui';

const LOADING_STEPS = [
  'Normalising source…',
  'Extracting ground truth…',
  'Running format agents in parallel…',
  'Verifying claims against source…',
  'Checking cross-format consistency…',
  'Finalising outputs…',
];

function SelectField({ id, label, value, onChange, options }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-xs font-medium text-ink-muted">{label}</label>
      <div className="relative">
        <select
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={cx(ui.field, 'omni-select appearance-none pr-9')}
        >
          {options.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
        <svg
          className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-ink-subtle"
          width="10" height="6" viewBox="0 0 10 6" fill="none" aria-hidden="true"
        >
          <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
    </div>
  );
}

export default function GenerationControls({
  tone, onToneChange,
  audience, onAudienceChange,
  tones, audiences,
  loading, loadingStep,
  error, canGenerate,
}) {
  const stepLabel = LOADING_STEPS[loadingStep % LOADING_STEPS.length];

  return (
    <div className="space-y-4 rounded-xl border border-line bg-surface p-5 shadow-panel">
      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField id="select-tone" label="Tone" value={tone} onChange={onToneChange} options={tones} />
        <SelectField id="select-audience" label="Target audience" value={audience} onChange={onAudienceChange} options={audiences} />
      </div>

      <div className="flex flex-col gap-3 rounded-lg border border-line bg-surface-2 p-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-sm font-medium text-ink">
            {loading ? 'Agents running' : 'Ready to generate'}
          </p>
          <p className="truncate text-xs text-ink-muted">
            {loading ? stepLabel : 'Each format runs as an independent specialised agent'}
          </p>
        </div>
        <button
          type="submit"
          disabled={loading || !canGenerate}
          aria-busy={loading}
          className={cx(ui.btnBase, ui.btnPrimary, ui.sizeMd, 'shrink-0 sm:w-auto')}
        >
          {loading ? (
            <>
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" aria-hidden="true" />
              Generating…
            </>
          ) : (
            'Generate outputs'
          )}
        </button>
      </div>

      {error && (
        <p className="rounded-md bg-danger-soft px-3 py-2 text-xs text-danger" role="alert">{error}</p>
      )}
    </div>
  );
}
