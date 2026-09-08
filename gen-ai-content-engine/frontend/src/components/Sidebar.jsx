import { useEffect } from 'react';

import { cx } from '../lib/ui';

/* ── Icons ─────────────────────────────────────────────────── */
const IconGrid = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <rect x="1.5" y="1.5" width="5.5" height="5.5" rx="1.5" fill="currentColor" />
    <rect x="9" y="1.5" width="5.5" height="5.5" rx="1.5" fill="currentColor" opacity="0.4" />
    <rect x="1.5" y="9" width="5.5" height="5.5" rx="1.5" fill="currentColor" opacity="0.4" />
    <rect x="9" y="9" width="5.5" height="5.5" rx="1.5" fill="currentColor" opacity="0.2" />
  </svg>
);
const IconHistory = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.25" />
    <path d="M8 5v3.25L10 9.75" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" />
  </svg>
);
const IconClose = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
    <path d="M2 2l9 9M11 2L2 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);
const IconChevron = ({ flip }) => (
  <svg
    width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"
    className={cx('transition-transform', flip && 'rotate-180')}
  >
    <path d="M8.5 2L4.5 6.5l4 4.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
const IconSignOut = () => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
    <path d="M6 13H3.5A1.5 1.5 0 0 1 2 11.5v-8A1.5 1.5 0 0 1 3.5 2H6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    <path d="M9.5 10.5 13 7 9.5 3.5M13 7H6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
const IconPlus = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
    <path d="M6.5 2v9M2 6.5h9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

function LogoMark() {
  return (
    <svg width="24" height="24" viewBox="0 0 22 22" fill="none" aria-hidden="true">
      <rect width="22" height="22" rx="6" fill="var(--color-accent)" opacity="0.16" />
      <rect x="5" y="5" width="5" height="5" rx="1.5" fill="var(--color-accent)" />
      <rect x="12" y="5" width="5" height="5" rx="1.5" fill="var(--color-accent)" opacity="0.55" />
      <rect x="5" y="12" width="5" height="5" rx="1.5" fill="var(--color-accent)" opacity="0.55" />
      <rect x="12" y="12" width="5" height="5" rx="1.5" fill="var(--color-accent)" opacity="0.28" />
    </svg>
  );
}

function NavItem({ icon, label, showLabel, active, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      title={!showLabel ? label : undefined}
      className={cx(
        'group flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-sm transition',
        !showLabel && 'justify-center',
        active
          ? 'bg-accent-soft text-ink'
          : 'text-ink-muted hover:bg-elevated hover:text-ink'
      )}
    >
      <span className={cx('shrink-0', active && 'text-accent')}>{icon}</span>
      {showLabel && <span className="min-w-0 flex-1 truncate text-left font-medium">{label}</span>}
    </button>
  );
}

export default function Sidebar({
  collapsed,
  onCollapseToggle,
  onHistory,
  onNewWorkspace,
  isMobile,
  drawerOpen,
  onDrawerClose,
  user,
  onSignOut,
}) {
  useEffect(() => {
    document.body.style.overflow = isMobile && drawerOpen ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [isMobile, drawerOpen]);

  const showLabels = isMobile || !collapsed;
  const width = isMobile ? 264 : collapsed ? 60 : 248;

  return (
    <aside
      aria-label="Primary navigation"
      style={{ width }}
      className={cx(
        'fixed inset-y-0 left-0 z-40 flex flex-col border-r border-line bg-surface/85 backdrop-blur-xl transition-transform duration-200',
        isMobile && !drawerOpen && '-translate-x-full'
      )}
    >
      {/* Header */}
      <div className="relative flex items-center justify-between gap-2 px-3.5 py-4">
        <div className={cx('flex items-center gap-2.5', !showLabels && 'w-full justify-center')}>
          <LogoMark />
          {showLabels && (
            <span className="text-[15px] font-semibold tracking-tight text-ink">OmniFormat AI</span>
          )}
        </div>
        <button
          type="button"
          onClick={isMobile ? onDrawerClose : onCollapseToggle}
          aria-label={isMobile ? 'Close navigation' : collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className={cx(
            'grid h-7 w-7 shrink-0 place-items-center rounded-md text-ink-subtle hover:bg-elevated hover:text-ink',
            !showLabels && 'absolute right-2 top-4'
          )}
        >
          {isMobile ? <IconClose /> : <IconChevron flip={collapsed} />}
        </button>
      </div>

      {/* New workspace */}
      <div className="px-2.5">
        <button
          type="button"
          onClick={onNewWorkspace}
          title={!showLabels ? 'New workspace' : undefined}
          className={cx(
            'flex w-full items-center gap-2 rounded-lg border border-line-strong bg-surface-2 px-2.5 py-2 text-sm font-medium text-ink transition hover:border-accent hover:bg-accent-soft',
            !showLabels && 'justify-center'
          )}
        >
          <IconPlus />
          {showLabels && 'New workspace'}
        </button>
      </div>

      {/* Nav */}
      <nav className="mt-3 flex-1 space-y-1 px-2.5" aria-label="Main navigation">
        <NavItem icon={<IconGrid />} label="Workspace" showLabel={showLabels} active onClick={onNewWorkspace} />
        <NavItem icon={<IconHistory />} label="History" showLabel={showLabels} onClick={onHistory} />
      </nav>

      {/* User + footer */}
      <div className="space-y-2 border-t border-line p-2.5">
        {user && (
          <div className={cx('flex items-center gap-2.5 rounded-lg border border-line bg-surface-2 p-2', !showLabels && 'justify-center')}>
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-semibold text-accent">
              {(user.displayName || user.email || '?').trim().charAt(0).toUpperCase()}
            </span>
            {showLabels && (
              <>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-ink" title={user.email}>
                    {user.displayName || user.email}
                  </p>
                  {user.isDev && <p className="text-[10px] text-warning">dev mode</p>}
                </div>
                <button
                  type="button"
                  onClick={onSignOut}
                  title="Sign out"
                  aria-label="Sign out"
                  className="shrink-0 rounded-md p-1 text-ink-subtle transition hover:bg-elevated hover:text-danger"
                >
                  <IconSignOut />
                </button>
              </>
            )}
          </div>
        )}
        {showLabels && (
          <p className="px-1 text-[10px] leading-relaxed text-ink-subtle">
            OmniFormat AI Engine · SIH26154
          </p>
        )}
      </div>
    </aside>
  );
}
