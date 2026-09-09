import { cx } from '../lib/ui';

const PROVIDER_LABEL = { groq: 'Groq', gemini: 'Gemini', openai: 'GPT', anthropic: 'Claude', ollama: 'Ollama' };
const PROVIDER_STYLE = {
  groq: 'bg-[#f9731633] text-[#fb923c]',
  gemini: 'bg-[#60a5fa33] text-[#93c5fd]',
  openai: 'bg-success-soft text-success',
  anthropic: 'bg-accent-soft text-accent',
};

function ProviderTag({ provider }) {
  if (!provider) return null;
  return (
    <span
      className={cx(
        'rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide',
        PROVIDER_STYLE[provider] || 'bg-inset text-ink-subtle'
      )}
      title={`Handled by ${PROVIDER_LABEL[provider] || provider}`}
    >
      {PROVIDER_LABEL[provider] || provider}
    </span>
  );
}

const FORMAT_DESCRIPTIONS = {
  advisory:          'Formal strategic advisory bulletin',
  executive_summary: 'Concise leadership-ready overview',
  linkedin:          'High-engagement professional post',
  x_thread:          'Numbered, shareable tweet thread',
  presentation:      'Slide deck with speaker notes',
  infographic:       'Structured stats, sections & a chart',
};

const FORMAT_META = {
  advisory:          '~500 words',
  executive_summary: '3–5 min read',
  linkedin:          '150–250 words',
  x_thread:          '5–8 tweets',
  presentation:      '7–10 slides',
  infographic:       'stats + chart',
};

const FORMAT_ICONS = {
  advisory:          '❖',
  executive_summary: '▤',
  linkedin:          'in',
  x_thread:          '#',
  presentation:      '▥',
  infographic:       '▦',
};

function CheckDot({ selected }) {
  return (
    <span
      aria-hidden="true"
      className={cx(
        'grid h-4 w-4 shrink-0 place-items-center rounded-[5px] border transition',
        selected ? 'border-accent bg-accent text-on-accent' : 'border-line-strong'
      )}
    >
      {selected && (
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
          <path d="M1.5 5l2.5 2.5L8.5 2.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </span>
  );
}

export default function OutputSelector({ outputs, onToggle, onToggleAll, options, routing = {} }) {
  const selectedCount = options.filter(({ key }) => outputs[key]).length;
  const allSelected = selectedCount === options.length;
  const hasRouting = Object.keys(routing).length > 0;

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs">
          <span className="rounded-full bg-accent-soft px-2 py-0.5 font-medium text-accent">
            {selectedCount} selected
          </span>
          <button
            type="button"
            onClick={() => onToggleAll(!allSelected)}
            className="font-medium text-ink-muted hover:text-ink"
          >
            {allSelected ? 'Clear all' : 'Select all'}
          </button>
        </div>
        <p className="hidden text-xs text-ink-subtle sm:block">
          {hasRouting ? 'Each format runs on its assigned model, in parallel' : 'Selected agents run concurrently'}
        </p>
      </div>

      <div className="grid gap-2 sm:grid-cols-2" role="group" aria-label="Output format selection">
        {options.map(({ key, label }) => {
          const selected = !!outputs[key];
          return (
            <button
              type="button"
              key={key}
              onClick={() => onToggle(key)}
              aria-pressed={selected}
              className={cx(
                'flex items-start gap-3 rounded-lg border p-3 text-left transition',
                selected
                  ? 'border-accent bg-accent-soft/50'
                  : 'border-line bg-surface-2 hover:border-line-strong hover:bg-elevated'
              )}
            >
              <CheckDot selected={selected} />
              <span
                aria-hidden="true"
                className={cx(
                  'grid h-7 w-7 shrink-0 place-items-center rounded-md text-xs font-semibold',
                  selected ? 'bg-accent text-on-accent' : 'bg-inset text-ink-muted'
                )}
              >
                {FORMAT_ICONS[key]}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-1.5">
                    <span className="text-sm font-medium text-ink">{label}</span>
                    <ProviderTag provider={routing[key]} />
                  </span>
                  <span className="shrink-0 text-[10px] text-ink-subtle">{FORMAT_META[key]}</span>
                </span>
                <span className="mt-0.5 block text-xs text-ink-muted">{FORMAT_DESCRIPTIONS[key] ?? ''}</span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
