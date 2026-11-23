'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import type { Session, User } from '@supabase/supabase-js';
import { supabase } from '@/lib/supabase';
import { AuthScreen } from '@/components/auth/AuthScreen';

interface AuthContextValue {
  session: Session | null;
  user: User;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const SESSION_RESTORE_TIMEOUT_MS = 8000;

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!supabase) {
      setIsLoading(false);
      return;
    }
    const authClient = supabase;

    let isMounted = true;
    let authEventReceived = false;
    const restoreTimeout = window.setTimeout(() => {
      if (!isMounted || authEventReceived) return;
      console.warn('Supabase session restoration timed out; showing sign-in screen while auth events remain active.');
      setSession(null);
      setIsLoading(false);
    }, SESSION_RESTORE_TIMEOUT_MS);

    let subscription: { unsubscribe: () => void } | undefined;
    try {
      const listener = authClient.auth.onAuthStateChange((_event, nextSession) => {
        if (isMounted) {
          authEventReceived = true;
          window.clearTimeout(restoreTimeout);
          setSession(nextSession);
          setIsLoading(false);
        }
      });
      subscription = listener.data.subscription;
    } catch (error) {
      console.error('Unable to subscribe to Supabase auth state changes:', error);
      window.clearTimeout(restoreTimeout);
      setSession(null);
      setIsLoading(false);
      return () => { isMounted = false; };
    }

    // Defer invocation into the promise chain so synchronous client/storage
    // initialization errors also reach the fallback that releases the screen.
    Promise.resolve()
      .then(() => authClient.auth.getSession())
      .then(({ data, error }) => {
        if (!isMounted) return;
        if (error) console.error('Unable to restore the Supabase session:', error.message);
        if (!authEventReceived) setSession(error ? null : data.session);
      })
      .catch((error: unknown) => {
        if (!isMounted) return;
        console.error('Unable to restore the Supabase session:', error);
        if (!authEventReceived) setSession(null);
      })
      .finally(() => {
        window.clearTimeout(restoreTimeout);
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
      window.clearTimeout(restoreTimeout);
      subscription?.unsubscribe();
    };
  }, []);

  const signOut = useCallback(async () => {
    if (!supabase) return;
    const { error } = await supabase.auth.signOut();
    if (error) throw error;
    setSession(null);
  }, []);

  if (!supabase) return <AuthScreen configurationMissing />;
  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 px-6 dark:bg-slate-950">
        <p className="text-sm text-slate-500 dark:text-slate-400" role="status">Restoring your secure session…</p>
      </main>
    );
  }
  if (!session) return <AuthScreen />;

  return (
    <AuthContext.Provider value={{ session, user: session.user, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider.');
  return context;
}
