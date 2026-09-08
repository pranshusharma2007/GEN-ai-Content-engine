/**
 * VersionBanner — shown when a loaded history run's source has been edited.
 * Lets the user surgically regenerate selected formats against the new source.
 */
import { useState } from 'react';

import { OUTPUT_OPTS } from '../lib/formats';
import { cx, ui } from '../lib/ui';

export default function VersionBanner({ sourceChanged, results, onRegenerate, regenLoading }) {
  const available = OUTPUT_OPTS.filter((o) => results && o.key in results);
  const [selected, setSelected] = useState(() => available.map((o) => o.key));

  if (!sourceChanged) return null;

  const toggle = (key) =>
    setSelected((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));

  return (
    <div className="mb-3 rounded-lg border border-accent/35 bg-accent-soft/60 p-3" role="alert" aria-live="polite">
      <div className="flex items-start gap-2.5">
        <span className="text-sm text-accent">⚡</span>
        <div>
          <p className="text-sm font-medium text-ink">Source changed</p>
          <p className="text-xs text-ink-muted">Pick which formats to regenerate with the updated source.</p>
        </div>
      </div>

      <div className="mt-2.5 flex flex-wrap gap-1.5">
        {available.map(({ key, label }) => {
          const on = selected.includes(key);
          return (
            <button
              key={key}
              type="button"
              onClick={() => toggle(key)}
              aria-pressed={on}
              className={cx(
                'rounded-full border px-2.5 py-1 text-xs font-medium transition',
                on ? 'border-accent bg-accent text-on-accent' : 'border-line-strong text-ink-muted hover:text-ink'
              )}
            >
              {on ? '✓ ' : ''}{label}
            </button>
          );
        })}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => onRegenerate(selected)}
          disabled={regenLoading || !selected.length}
          className={cx(ui.btnBase, ui.btnPrimary, ui.sizeSm)}
        >
          {regenLoading ? 'Regenerating…' : `Regenerate ${selected.length} format${selected.length !== 1 ? 's' : ''}`}
        </button>
        <button
          type="button"
          onClick={() => onRegenerate(available.map((o) => o.key))}
          disabled={regenLoading}
          className={cx(ui.btnBase, ui.btnGhost, ui.sizeSm)}
        >
          Regenerate all
        </button>
      </div>
    </div>
  );
}
