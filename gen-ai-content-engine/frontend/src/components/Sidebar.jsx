import { useEffect } from 'react';

/* ── Icons ─────────────────────────────────────────────────── */
function IconGrid() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <rect x="1.5" y="1.5" width="5.5" height="5.5" rx="1.5" fill="currentColor" />
      <rect x="9" y="1.5" width="5.5" height="5.5" rx="1.5" fill="currentColor" opacity="0.4" />
      <rect x="1.5" y="9" width="5.5" height="5.5" rx="1.5" fill="currentColor" opacity="0.4" />
      <rect x="9" y="9" width="5.5" height="5.5" rx="1.5" fill="currentColor" opacity="0.2" />
    </svg>
  );
}

function IconHistory() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.25" />
      <path d="M8 5v3.25L10 9.75" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" />
    </svg>
  );
}

function IconClose() {
  return (
    <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
      <path d="M2 2l9 9M11 2L2 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function IconChevron() {
  return (
    <svg className="sidebar-chevron" width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
      <path d="M8.5 2L4.5 6.5l4 4.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* ── Logo mark ──────────────────────────────────────────────── */
function LogoMark() {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
      <rect width="22" height="22" rx="6" fill="var(--accent)" opacity="0.15" />
      <rect x="5" y="5" width="5" height="5" rx="1.5" fill="var(--accent)" />
      <rect x="12" y="5" width="5" height="5" rx="1.5" fill="var(--accent)" opacity="0.5" />
      <rect x="5" y="12" width="5" height="5" rx="1.5" fill="var(--accent)" opacity="0.5" />
      <rect x="12" y="12" width="5" height="5" rx="1.5" fill="var(--accent)" opacity="0.25" />
    </svg>
  );
}

/* ── Sidebar ────────────────────────────────────────────────── */
export default function Sidebar({
  collapsed,
  onCollapseToggle,
  onHistory,
  onNewWorkspace,
  isMobile,
  drawerOpen,
  onDrawerClose,
}) {
  useEffect(() => {
    document.body.style.overflow = (isMobile && drawerOpen) ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [isMobile, drawerOpen]);

  const showLabels = isMobile || !collapsed;

  const cls = [
    'sidebar',
    !isMobile && collapsed ? 'sidebar--collapsed' : '',
    isMobile              ? 'sidebar--mobile'    : '',
    isMobile && drawerOpen ? 'sidebar--open'     : '',
  ].filter(Boolean).join(' ');

  return (
    <aside className={cls} aria-label="Primary navigation">
      {/* Header */}
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <div className="sidebar-logo-mark"><LogoMark /></div>
          {showLabels && <span className="sidebar-logo-text">OmniFormat AI</span>}
        </div>

        {isMobile ? (
          <button type="button" className="sidebar-icon-btn" onClick={onDrawerClose} aria-label="Close navigation">
            <IconClose />
          </button>
        ) : (
          <button
            type="button"
            className="sidebar-icon-btn"
            onClick={onCollapseToggle}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <IconChevron />
          </button>
        )}
      </div>

      {/* Nav */}
      <nav className="sidebar-nav" aria-label="Main navigation">
        <ul className="sidebar-nav-list" role="list">
          <li>
            <button
              type="button"
              className="sidebar-nav-item sidebar-nav-item--active"
              onClick={onNewWorkspace}
              aria-current="page"
              title={!showLabels ? 'Workspace' : undefined}
            >
              <span className="sidebar-nav-icon"><IconGrid /></span>
              {showLabels && <span className="sidebar-nav-label">Workspace</span>}
              {showLabels && (
                <button
                  type="button"
                  className="sidebar-new-workspace"
                  onClick={(e) => { e.stopPropagation(); onNewWorkspace?.(); }}
                  title="New workspace"
                  aria-label="New workspace"
                >+</button>
              )}
            </button>
          </li>
          <li>
            <button
              type="button"
              className="sidebar-nav-item"
              onClick={onHistory}
              title={!showLabels ? 'History' : undefined}
            >
              <span className="sidebar-nav-icon"><IconHistory /></span>
              {showLabels && <span className="sidebar-nav-label">History</span>}
            </button>
          </li>
        </ul>
      </nav>

      {/* Footer branding */}
      {showLabels && (
        <div className="sidebar-footer">
          <span className="sidebar-footer-text">OmniFormat AI Engine</span>
          <span className="sidebar-footer-sub">SIH26154 · Team WildCard</span>
        </div>
      )}
    </aside>
  );
}
