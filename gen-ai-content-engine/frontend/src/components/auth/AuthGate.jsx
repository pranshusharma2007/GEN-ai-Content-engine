import { useAuth } from '../../context/AuthContext';
import LoginScreen from './LoginScreen';

export default function AuthGate({ children }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center bg-canvas">
        <div className="flex flex-col items-center gap-3">
          <span className="h-6 w-6 animate-spin rounded-full border-2 border-line-strong border-t-accent" />
          <span className="text-sm text-ink-subtle">Loading workspace…</span>
        </div>
      </div>
    );
  }

  if (!user) return <LoginScreen />;

  return children;
}
