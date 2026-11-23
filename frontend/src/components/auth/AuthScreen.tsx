'use client';

import { FormEvent, useState } from 'react';
import { AlertCircle, FileText, LoaderCircle, ShieldCheck } from 'lucide-react';
import { supabase } from '@/lib/supabase';

export function AuthScreen({ configurationMissing = false }: { configurationMissing?: boolean }) {
  const [mode, setMode] = useState<'sign-in' | 'sign-up'>('sign-in');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!supabase) return;

    setIsSubmitting(true);
    setErrorMessage('');
    setSuccessMessage('');
    try {
      if (mode === 'sign-up') {
        const { data, error } = await supabase.auth.signUp({ email, password });
        if (error) throw error;
        if (!data.session) {
          setSuccessMessage('Account created. Check your email to confirm your address, then sign in.');
        }
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Authentication failed. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10 dark:bg-slate-950">
      <section className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-7 shadow-xl shadow-slate-200/50 dark:border-slate-800 dark:bg-slate-900 dark:shadow-black/20 sm:p-9">
        <div className="mb-7 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-500/10 text-brand-600 dark:text-brand-400">
            <FileText className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900 dark:text-white">FormEase</h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">Understand documents, step by step.</p>
          </div>
        </div>

        {configurationMissing ? (
          <div className="space-y-4" role="alert">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Connect your Supabase project</h2>
            <p className="text-sm leading-6 text-slate-600 dark:text-slate-300">
              Authentication uses Supabase Auth. Add your project URL and public anon key to <code className="rounded bg-slate-100 px-1.5 py-0.5 dark:bg-slate-800">frontend/.env.local</code>, then restart the frontend.
            </p>
            <p className="rounded-xl bg-amber-50 p-3 text-xs leading-5 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
              Use only the public anon/publishable key here. Never use the service-role key in frontend configuration.
            </p>
          </div>
        ) : (
          <>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
              {mode === 'sign-in' ? 'Sign in to your account' : 'Create your account'}
            </h2>
            <p className="mb-6 mt-1 text-sm text-slate-500 dark:text-slate-400">
              Your documents are saved to your private account.
            </p>

            {errorMessage && (
              <div className="mb-4 flex gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300" role="alert">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{errorMessage}</span>
              </div>
            )}
            {successMessage && (
              <p className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300" role="status">
                {successMessage}
              </p>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label htmlFor="auth-email" className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">Email</label>
                <input id="auth-email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} className="w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 dark:border-slate-700 dark:bg-slate-950 dark:text-white" />
              </div>
              <div>
                <label htmlFor="auth-password" className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">Password</label>
                <input id="auth-password" type="password" autoComplete={mode === 'sign-in' ? 'current-password' : 'new-password'} minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} className="w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 dark:border-slate-700 dark:bg-slate-950 dark:text-white" />
                {mode === 'sign-up' && <p className="mt-1 text-xs text-slate-500">Use at least 8 characters.</p>}
              </div>
              <button type="submit" disabled={isSubmitting} className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60">
                {isSubmitting ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                {isSubmitting ? 'Please wait…' : mode === 'sign-in' ? 'Sign in' : 'Create account'}
              </button>
            </form>

            <p className="mt-6 text-center text-sm text-slate-600 dark:text-slate-400">
              {mode === 'sign-in' ? 'New to FormEase?' : 'Already have an account?'}{' '}
              <button type="button" onClick={() => { setMode(mode === 'sign-in' ? 'sign-up' : 'sign-in'); setErrorMessage(''); setSuccessMessage(''); }} className="font-semibold text-brand-700 hover:underline dark:text-brand-400">
                {mode === 'sign-in' ? 'Create an account' : 'Sign in'}
              </button>
            </p>
          </>
        )}
      </section>
    </main>
  );
}
