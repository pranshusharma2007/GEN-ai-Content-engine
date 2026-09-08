/**
 * AuthContext — wraps Firebase Auth and exposes a small, stable API to the app.
 *
 * When Firebase is not configured, this falls back to a local "dev user" so the
 * workspace remains fully usable during development / offline demos. The backend
 * mirrors this behaviour (see backend/auth.py).
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import {
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
} from 'firebase/auth';

import { auth, googleProvider, isFirebaseConfigured } from '../lib/firebase';

const DEV_USER = {
  uid: 'dev-user',
  email: 'dev@local',
  displayName: 'Dev User',
  isDev: true,
};

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(isFirebaseConfigured ? null : DEV_USER);
  const [loading, setLoading] = useState(isFirebaseConfigured);
  const [error, setError]     = useState('');

  useEffect(() => {
    if (!isFirebaseConfigured || !auth) return undefined;
    return onAuthStateChanged(auth, (fbUser) => {
      setUser(
        fbUser
          ? {
              uid: fbUser.uid,
              email: fbUser.email,
              displayName: fbUser.displayName || fbUser.email,
              photoURL: fbUser.photoURL || null,
            }
          : null
      );
      setLoading(false);
    });
  }, []);

  const wrap = useCallback((fn) => async (...args) => {
    setError('');
    try {
      return await fn(...args);
    } catch (e) {
      setError(prettyAuthError(e));
      throw e;
    }
  }, []);

  const signUp = useMemo(
    () => wrap((email, password) => createUserWithEmailAndPassword(auth, email, password)),
    [wrap]
  );
  const signIn = useMemo(
    () => wrap((email, password) => signInWithEmailAndPassword(auth, email, password)),
    [wrap]
  );
  const signInWithGoogle = useMemo(
    () => wrap(() => signInWithPopup(auth, googleProvider)),
    [wrap]
  );

  const signOutUser = useCallback(async () => {
    if (!isFirebaseConfigured || !auth) return;
    await signOut(auth);
  }, []);

  /** Returns a fresh Firebase ID token, or null in dev-bypass mode. */
  const getToken = useCallback(async () => {
    if (!isFirebaseConfigured || !auth?.currentUser) return null;
    return auth.currentUser.getIdToken();
  }, []);

  const value = useMemo(
    () => ({
      user,
      loading,
      error,
      isDevBypass: !isFirebaseConfigured,
      signUp,
      signIn,
      signInWithGoogle,
      signOutUser,
      getToken,
      clearError: () => setError(''),
    }),
    [user, loading, error, signUp, signIn, signInWithGoogle, signOutUser, getToken]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>');
  return ctx;
}

function prettyAuthError(e) {
  const code = e?.code || '';
  const map = {
    'auth/invalid-email': 'That email address is not valid.',
    'auth/user-disabled': 'This account has been disabled.',
    'auth/user-not-found': 'No account found for that email.',
    'auth/wrong-password': 'Incorrect password.',
    'auth/invalid-credential': 'Incorrect email or password.',
    'auth/email-already-in-use': 'An account already exists for that email.',
    'auth/weak-password': 'Password should be at least 6 characters.',
    'auth/popup-closed-by-user': 'Sign-in was cancelled.',
    'auth/too-many-requests': 'Too many attempts. Try again in a moment.',
  };
  return map[code] || e?.message || 'Authentication failed. Please try again.';
}
