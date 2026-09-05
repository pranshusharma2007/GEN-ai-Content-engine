/**
 * VersionBanner — shown when a history run's source has been modified.
 * Lets the user select which formats to regenerate surgically.
 */
import { useState } from 'react';
import { OUTPUT_OPTS } from '../App';

export default function VersionBanner({ sourceChanged, results, onRegenerate, regenLoading }) {
  const [selected, setSelected] = useState(() => {
    // Pre-select all formats that are currently in the result set
    return (OUTPUT_OPTS.map(o => o.key).filter(k => results && k in results));
  });

  if (!sourceChanged) return null;

  const toggle = (key) => {
    setSelected(prev =>
      prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
    );
  };

  const availableFormats = OUTPUT_OPTS.filter(o => results && o.key in results);

  return (
    <div className="version-banner" role="alert" aria-live="polite">
      <div className="version-banner-header">
        <span className="version-banner-icon">⚡</span>
        <div className="version-banner-text">
          <strong>Source changed</strong>
          <span>Select which formats to regenerate with the updated source.</span>
        </div>
      </div>

      <div className="version-banner-formats">
        {availableFormats.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            className={`version-format-btn${selected.includes(key) ? ' version-format-btn--selected' : ''}`}
            onClick={() => toggle(key)}
            aria-pressed={selected.includes(key)}
          >
            {selected.includes(key) ? '✓ ' : ''}{label}
          </button>
        ))}
      </div>

      <div className="version-banner-actions">
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={() => onRegenerate(selected)}
          disabled={regenLoading || !selected.length}
        >
          {regenLoading ? 'Regenerating…' : `Regenerate ${selected.length} format${selected.length !== 1 ? 's' : ''}`}
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => onRegenerate(availableFormats.map(o => o.key))}
          disabled={regenLoading}
        >
          Regenerate all
        </button>
      </div>
    </div>
  );
}
