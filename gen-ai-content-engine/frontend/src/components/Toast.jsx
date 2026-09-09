import { cx } from '../lib/ui';

export default function Toast({ message, visible }) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      aria-hidden={!visible}
      className={cx(
        'fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-full border border-line-strong bg-elevated px-4 py-2 text-sm text-ink shadow-pop transition-all duration-200',
        visible ? 'translate-y-0 opacity-100' : 'pointer-events-none translate-y-3 opacity-0'
      )}
    >
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
        <path d="M2.5 7L5.5 10L11.5 4" stroke="var(--color-success)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {message}
    </div>
  );
}
