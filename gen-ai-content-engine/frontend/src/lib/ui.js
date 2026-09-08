/** Tiny classname joiner. */
export function cx(...parts) {
  return parts.filter(Boolean).join(' ');
}

/** Shared control class strings so buttons/inputs stay consistent app-wide. */
export const ui = {
  btnBase:
    'inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium transition ' +
    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ' +
    'disabled:cursor-not-allowed disabled:opacity-55',
  btnPrimary: 'bg-accent text-on-accent hover:bg-accent-hover active:bg-accent-press',
  btnGhost:
    'border border-line-strong bg-surface-2 text-ink hover:border-ink-subtle hover:bg-elevated',
  btnSubtle: 'text-ink-muted hover:bg-elevated hover:text-ink',
  sizeSm: 'px-2.5 py-1.5 text-xs',
  sizeMd: 'px-4 py-2.5',
  field:
    'w-full rounded-lg border border-line-strong bg-inset px-3.5 py-2.5 text-sm text-ink ' +
    'placeholder:text-ink-subtle outline-none transition focus:border-accent focus:ring-2 focus:ring-accent-ring',
  card: 'rounded-xl border border-line bg-surface',
  label: 'text-xs font-medium text-ink-muted',
};
