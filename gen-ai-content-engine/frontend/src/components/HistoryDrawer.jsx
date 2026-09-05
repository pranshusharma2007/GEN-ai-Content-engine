export default function HistoryDrawer({ isOpen, onClose, history, error, onSelect }) {
  return (
    <aside className={`history-drawer ${isOpen ? 'history-drawer--open' : ''}`} aria-label="Transformation history">
      <div className="history-drawer-header">
        <h2>History</h2>
        <button onClick={onClose} className="history-drawer-close" aria-label="Close history">
          &times;
        </button>
      </div>

      <div className="history-drawer-content">
        {error && <p className="history-error" role="alert">{error}</p>}

        {!error && !history.length ? (
          <p className="section-helper" style={{ padding: 16 }}>
            No transformations saved yet. Run a generation to start building history.
          </p>
        ) : (
          history.map((item) => {
            const formats = item.parameters?.formats ?? [];
            const sourceType = item.source?.type ?? 'text';
            const preview = item.source?.preview ?? '';
            const date = item.created_at
              ? new Date(item.created_at).toLocaleString(undefined, {
                  month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                })
              : '—';

            const sourceIcon = {
              text: '¶', pdf: 'PDF', docx: 'DOCX', url: '🔗',
            }[sourceType] ?? '¶';

            return (
              <div key={item.run_id} className="history-card">
                <div className="history-card-header">
                  <span className="history-card-date">{date}</span>
                  <span className="history-source-badge">{sourceIcon}</span>
                </div>
                <p className="history-card-source">{preview || '(no preview)'}</p>
                <p className="history-card-outputs">
                  {formats.map((f) => f.replace(/_/g, ' ')).join(' · ')}
                </p>
                <div className="history-card-actions">
                  <button
                    onClick={() => onSelect(item)}
                    className="history-card-load"
                    aria-label={`Load run from ${date}`}
                  >
                    Load run
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
