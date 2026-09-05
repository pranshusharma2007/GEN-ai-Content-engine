const FORMAT_DESCRIPTIONS = {
  advisory:          'Formal strategic advisory bulletin',
  executive_summary: 'Concise leadership-ready overview',
  linkedin:          'High-engagement professional post',
  x_thread:          'Numbered, shareable tweet thread',
  presentation:      'Slide-by-slide deck with speaker notes',
};

const FORMAT_META = {
  advisory:          'Approx. 500 words',
  executive_summary: '3–5 min read',
  linkedin:          '150–250 words',
  x_thread:          '5–8 tweets',
  presentation:      '7–10 slides',
};

const FORMAT_ICONS = {
  advisory:          '◌',
  executive_summary: '▤',
  linkedin:          'in',
  x_thread:          '#',
  presentation:      '▥',
};

export default function OutputSelector({ outputs, onToggle, onToggleAll, options }) {
  const selectedCount = options.filter(({ key }) => outputs[key]).length;
  const allSelected   = selectedCount === options.length;
  const noneSelected  = selectedCount === 0;

  return (
    <div className="output-selector">
      {/* Header row */}
      <div className="output-selector-header">
        <div className="output-meta">
          <span className="output-count">{selectedCount} selected</span>
          <button
            type="button"
            className="text-btn"
            onClick={() => onToggleAll(!allSelected)}
          >
            {allSelected ? 'Clear all' : 'Select all'}
          </button>
        </div>
        <p className="output-selector-hint">All selected agents run concurrently</p>
      </div>

      {/* Format rows */}
      <div className="output-list" role="group" aria-label="Output format selection">
        {options.map(({ key, label }) => {
          const selected = !!outputs[key];
          return (
            <button
              type="button"
              key={key}
              className={`output-row${selected ? ' output-row--selected' : ''}`}
              onClick={() => onToggle(key)}
              aria-pressed={selected}
              aria-label={`${label}: ${selected ? 'selected' : 'not selected'}`}
            >
              <span className="output-indicator" aria-hidden="true">
                <span className="output-indicator-dot" />
              </span>
              <div className="output-content">
                <span className="output-icon" aria-hidden="true">{FORMAT_ICONS[key]}</span>
                <span className="output-name">{label}</span>
                <span className="output-desc">{FORMAT_DESCRIPTIONS[key] ?? ''}</span>
              </div>
              <span className="output-format-meta">{FORMAT_META[key]}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
