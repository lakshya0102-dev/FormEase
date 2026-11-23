import { createClient } from '@supabase/supabase-js';
import { frontendEnv, hasSupabaseConfig } from '@/lib/env';

export const supabase = hasSupabaseConfig
  ? createClient(frontendEnv.supabaseUrl!, frontendEnv.supabaseAnonKey!)
  : null;

export function requireSupabase() {
  if (!supabase) {
    throw new Error(
      'Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in frontend/.env.local.',
    );
  }

  return supabase;
}
