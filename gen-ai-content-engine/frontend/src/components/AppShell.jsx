import { useEffect, useState } from 'react';

import Sidebar from './Sidebar';

/** Full-bleed backdrop: soft indigo glow + faint dot grid. Pure CSS, no canvas. */
function Backdrop() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-canvas">
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(46rem 32rem at 12% -8%, rgba(99,102,241,0.16), transparent 60%),' +
            'radial-gradient(40rem 30rem at 100% 0%, rgba(52,211,153,0.07), transparent 55%)',
        }}
      />
      <div
        className="absolute inset-0 opacity-35"
        style={{
          backgroundImage: 'radial-gradient(rgba(255,255,255,0.05) 1px, transparent 1px)',
          backgroundSize: '22px 22px',
          maskImage: 'radial-gradient(60rem 60rem at 30% 0%, black, transparent 75%)',
        }}
      />
    </div>
  );
}

export default function AppShell({ onHistory, onNewWorkspace, user, onSignOut, children }) {
  const [collapsed, setCollapsed] = useState(
    () => typeof window !== 'undefined' && window.innerWidth < 1024
  );
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && window.innerWidth < 768
  );

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 767px)');
    const handle = (e) => { setIsMobile(e.matches); if (!e.matches) setDrawerOpen(false); };
    mq.addEventListener('change', handle);
    return () => mq.removeEventListener('change', handle);
  }, []);

  const marginLeft = isMobile ? 0 : collapsed ? 60 : 248;

  return (
    <div className="relative flex min-h-screen w-full max-w-full overflow-x-hidden">
      <Backdrop />

      {isMobile && drawerOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/55 backdrop-blur-[2px]"
          onClick={() => setDrawerOpen(false)}
          aria-hidden="true"
        />
      )}

      <Sidebar
        collapsed={collapsed}
        onCollapseToggle={() => setCollapsed((c) => !c)}
        onHistory={onHistory}
        onNewWorkspace={onNewWorkspace}
        isMobile={isMobile}
        drawerOpen={drawerOpen}
        onDrawerClose={() => setDrawerOpen(false)}
        user={user}
        onSignOut={onSignOut}
      />

      <div className="min-w-0 flex-1 overflow-x-hidden transition-[margin] duration-200" style={{ marginLeft }}>
        {isMobile && (
          <div className="sticky top-0 z-20 flex items-center gap-3 border-b border-line bg-canvas/80 px-4 py-3 backdrop-blur">
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              aria-label="Open navigation"
              aria-expanded={drawerOpen}
              className="grid h-8 w-8 place-items-center rounded-md text-ink-muted hover:bg-elevated"
            >
              <svg width="16" height="12" viewBox="0 0 16 12" fill="none" aria-hidden="true">
                <rect y="0" width="16" height="1.5" rx="0.75" fill="currentColor" />
                <rect y="5.25" width="16" height="1.5" rx="0.75" fill="currentColor" />
                <rect y="10.5" width="16" height="1.5" rx="0.75" fill="currentColor" />
              </svg>
            </button>
            <span className="text-sm font-semibold tracking-tight">OmniFormat AI</span>
          </div>
        )}
        {children}
      </div>
    </div>
  );
}
