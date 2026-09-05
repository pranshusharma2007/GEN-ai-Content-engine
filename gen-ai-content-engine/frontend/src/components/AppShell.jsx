import { useState, useEffect } from 'react';
import Sidebar from './Sidebar';
import DitherWave from './DitherWave';

export default function AppShell({ onHistory, onNewWorkspace, children }) {
  const [collapsed, setCollapsed] = useState(
    () => typeof window !== 'undefined' && window.innerWidth < 1024
  );
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [isMobile,   setIsMobile]   = useState(
    () => typeof window !== 'undefined' && window.innerWidth < 768
  );

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 767px)');
    const handle = (e) => { setIsMobile(e.matches); if (!e.matches) setDrawerOpen(false); };
    mq.addEventListener('change', handle);
    return () => mq.removeEventListener('change', handle);
  }, []);

  const sidebarWidth = isMobile ? 0 : collapsed ? 'var(--sidebar-min)' : 'var(--sidebar-w)';

  return (
    <div className="shell">
      <div className="background-layer"><DitherWave /></div>

      {isMobile && drawerOpen && (
        <div className="shell-overlay" onClick={() => setDrawerOpen(false)} aria-hidden="true" />
      )}

      <Sidebar
        collapsed={collapsed}
        onCollapseToggle={() => setCollapsed((c) => !c)}
        onHistory={onHistory}
        onNewWorkspace={onNewWorkspace}
        isMobile={isMobile}
        drawerOpen={drawerOpen}
        onDrawerClose={() => setDrawerOpen(false)}
      />

      <div className="shell-main" style={{ marginLeft: sidebarWidth }}>
        {isMobile && (
          <div className="mobile-topbar">
            <button
              type="button"
              className="mobile-menu-btn"
              onClick={() => setDrawerOpen(true)}
              aria-label="Open navigation"
              aria-expanded={drawerOpen}
            >
              <svg width="16" height="12" viewBox="0 0 16 12" fill="none" aria-hidden="true">
                <rect y="0"    width="16" height="1.5" rx="0.75" fill="currentColor" />
                <rect y="5.25" width="16" height="1.5" rx="0.75" fill="currentColor" />
                <rect y="10.5" width="16" height="1.5" rx="0.75" fill="currentColor" />
              </svg>
            </button>
            <span className="mobile-topbar-title">OmniFormat AI</span>
          </div>
        )}
        {children}
      </div>
    </div>
  );
}
