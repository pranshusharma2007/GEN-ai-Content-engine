import { cx } from '../lib/ui';

export default function HistoryDrawer({ isOpen, onClose, history, error, onSelect }) {
  return (
    <>
      <div
        className={cx(
          'fixed inset-0 z-40 bg-black/50 transition-opacity duration-200',
          isOpen ? 'opacity-100' : 'pointer-events-none opacity-0'
        )}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        aria-label="Transformation history"
        className={cx(
          'fixed inset-y-0 right-0 z-50 flex w-full max-w-sm flex-col border-l border-line bg-surface shadow-pop transition-transform duration-300',
          isOpen ? 'translate-x-0' : 'translate-x-full'
        )}
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="text-sm font-semibold text-ink">History</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close history"
            className="grid h-7 w-7 place-items-center rounded-md text-ink-subtle hover:bg-elevated hover:text-ink"
          >
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
              <path d="M2 2l9 9M11 2L2 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <div className="flex-1 space-y-2.5 overflow-y-auto p-4">
          {error && (
            <p className="rounded-md bg-danger-soft px-3 py-2 text-xs text-danger" role="alert">{error}</p>
          )}

          {!error && !history.length && (
            <p className="px-1 py-8 text-center text-xs text-ink-subtle">
              No transformations saved yet. Run a generation to start building history.
            </p>
          )}

          {history.map((item) => {
            const formats = item.parameters?.formats ?? [];
            const sourceType = item.source?.type ?? 'text';
            const preview = item.source?.preview ?? '';
            const date = item.created_at
              ? new Date(item.created_at).toLocaleString(undefined, {
                  month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                })
              : '—';
            const score = item.consistency?.consistency_score;
            const scoreColor = score == null ? 'text-ink-subtle'
              : score >= 90 ? 'text-success'
              : score >= 70 ? 'text-warning'
              : 'text-danger';

            return (
              <button
                key={item.run_id}
                type="button"
                onClick={() => onSelect(item)}
                className="w-full rounded-lg border border-line bg-surface-2 p-3 text-left transition hover:border-line-strong hover:bg-elevated"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs text-ink-subtle">{date}</span>
                  <div className="flex items-center gap-2">
                    {score != null && (
                      <span className={cx('text-[11px] font-medium', scoreColor)} title={`Consistency ${score}/100`}>
                        ◉ {score}
                      </span>
                    )}
                    <span className="rounded bg-inset px-1.5 py-0.5 text-[10px] font-medium uppercase text-ink-subtle">
                      {sourceType}
                    </span>
                  </div>
                </div>
                <p className="mt-1.5 line-clamp-2 text-xs text-ink-muted">{preview || '(no preview)'}</p>
                <p className="mt-1.5 text-[11px] text-ink-subtle">
                  {formats.length} format{formats.length !== 1 ? 's' : ''} · {formats.map((f) => f.replace(/_/g, ' ')).join(' · ')}
                </p>
              </button>
            );
          })}
        </div>
      </aside>
    </>
  );
}
