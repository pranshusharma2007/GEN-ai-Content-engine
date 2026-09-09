import { useState } from 'react';

import { useAuth } from '../../context/AuthContext';
import { isFirebaseConfigured } from '../../lib/firebase';
import { cx, ui } from '../../lib/ui';

function LogoMark({ className = 'h-9 w-9' }) {
  return (
    <svg viewBox="0 0 22 22" fill="none" className={className} aria-hidden="true">
      <rect width="22" height="22" rx="6" fill="var(--color-accent)" opacity="0.16" />
      <rect x="5" y="5" width="5" height="5" rx="1.5" fill="var(--color-accent)" />
      <rect x="12" y="5" width="5" height="5" rx="1.5" fill="var(--color-accent)" opacity="0.55" />
      <rect x="5" y="12" width="5" height="5" rx="1.5" fill="var(--color-accent)" opacity="0.55" />
      <rect x="12" y="12" width="5" height="5" rx="1.5" fill="var(--color-accent)" opacity="0.28" />
    </svg>
  );
}

function GoogleGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 18 18" aria-hidden="true">
      <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62Z" />
      <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18Z" />
      <path fill="#FBBC05" d="M3.97 10.72A5.4 5.4 0 0 1 3.68 9c0-.6.1-1.18.29-1.72V4.95H.96A9 9 0 0 0 0 9c0 1.45.35 2.82.96 4.05l3.01-2.33Z" />
      <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58Z" />
    </svg>
  );
}

export default function LoginScreen() {
  const { signIn, signUp, signInWithGoogle, error, clearError } = useAuth();
  const [mode, setMode]         = useState('signin');
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy]         = useState(false);

  const isSignup = mode === 'signup';

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (isSignup) await signUp(email.trim(), password);
      else await signIn(email.trim(), password);
    } catch { /* surfaced via context */ } finally {
      setBusy(false);
    }
  };

  const google = async () => {
    setBusy(true);
    try { await signInWithGoogle(); } catch { /* handled */ } finally { setBusy(false); }
  };

  const swap = () => { clearError(); setMode(isSignup ? 'signin' : 'signup'); };

  return (
    <div className="grid min-h-screen w-full bg-canvas lg:grid-cols-[1.05fr_1fr]">
      {/* Brand panel */}
      <aside className="relative hidden overflow-hidden border-r border-line bg-surface lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div
          className="pointer-events-none absolute inset-0 opacity-80"
          style={{
            background:
              'radial-gradient(60% 50% at 15% 10%, rgba(99,102,241,0.22), transparent 70%),' +
              'radial-gradient(50% 60% at 90% 90%, rgba(52,211,153,0.12), transparent 70%)',
          }}
        />
        <div className="relative flex items-center gap-2.5">
          <LogoMark />
          <span className="text-[15px] font-semibold tracking-tight text-ink">OmniFormat AI</span>
        </div>

        <div className="relative max-w-md">
          <h1 className="text-[2rem] font-semibold leading-tight tracking-tight text-ink">
            One source in.<br />A full communications package out.
          </h1>
          <p className="mt-4 text-sm leading-relaxed text-ink-muted">
            Paste a report, advisory, or article. Pick your formats. Specialised agents run
            in parallel and every claim is traced back to the source.
          </p>
          <ul className="mt-7 space-y-3 text-sm text-ink-muted">
            {['Parallel multi-agent generation', 'Claim-level source grounding', 'Real .pptx / .pdf export'].map((t) => (
              <li key={t} className="flex items-center gap-3">
                <span className="grid h-5 w-5 place-items-center rounded-full bg-accent-soft text-[11px] text-accent">✓</span>
                {t}
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-ink-subtle">SIH26154 · Team WildCard</p>
      </aside>

      {/* Form panel */}
      <main className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <LogoMark className="h-8 w-8" />
            <span className="text-[15px] font-semibold tracking-tight">OmniFormat AI</span>
          </div>

          <h2 className="text-xl font-semibold tracking-tight text-ink">
            {isSignup ? 'Create your account' : 'Sign in to your workspace'}
          </h2>
          <p className="mt-1.5 text-sm text-ink-muted">
            {isSignup ? 'Start transforming source content in seconds.' : 'Welcome back.'}
          </p>

          {!isFirebaseConfigured && (
            <div className="mt-5 rounded-lg border border-warning/30 bg-warning-soft px-3.5 py-2.5 text-xs text-warning">
              Firebase is not configured — add <code>VITE_FIREBASE_*</code> to <code>.env</code>. Continue below in dev mode.
            </div>
          )}

          <form onSubmit={submit} className="mt-6 space-y-3.5">
            <div>
              <label htmlFor="email" className="mb-1.5 block text-xs font-medium text-ink-muted">Email</label>
              <input
                id="email" type="email" required autoComplete="email"
                className={ui.field}
                placeholder="you@organisation.gov"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="password" className="mb-1.5 block text-xs font-medium text-ink-muted">Password</label>
              <input
                id="password" type="password" required
                autoComplete={isSignup ? 'new-password' : 'current-password'}
                className={ui.field}
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            {error && (
              <p className="rounded-md bg-danger-soft px-3 py-2 text-xs text-danger" role="alert">{error}</p>
            )}

            <button type="submit" disabled={busy} className={cx(ui.btnBase, ui.btnPrimary, ui.sizeMd, 'mt-1 w-full')}>
              {busy ? 'Please wait…' : isSignup ? 'Create account' : 'Sign in'}
            </button>
          </form>

          <div className="my-5 flex items-center gap-3 text-[11px] uppercase tracking-wide text-ink-subtle">
            <span className="h-px flex-1 bg-line" />or<span className="h-px flex-1 bg-line" />
          </div>

          <button
            type="button"
            onClick={google}
            disabled={busy || !isFirebaseConfigured}
            className={cx(ui.btnBase, ui.btnGhost, ui.sizeMd, 'w-full')}
          >
            <GoogleGlyph />
            Continue with Google
          </button>

          <p className="mt-6 text-center text-sm text-ink-muted">
            {isSignup ? 'Already have an account?' : 'New to OmniFormat?'}{' '}
            <button type="button" onClick={swap} className="font-medium text-accent hover:underline">
              {isSignup ? 'Sign in' : 'Create one'}
            </button>
          </p>
        </div>
      </main>
    </div>
  );
}
