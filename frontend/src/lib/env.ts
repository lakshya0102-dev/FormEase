function normalizeOptionalEnv(value: string | undefined): string | undefined {
  const normalized = value?.trim();
  return normalized || undefined;
}

export const frontendEnv = {
  apiUrl: (normalizeOptionalEnv(process.env.NEXT_PUBLIC_API_URL) ?? '/api/v1').replace(/\/$/, ''),
  supabaseUrl: normalizeOptionalEnv(process.env.NEXT_PUBLIC_SUPABASE_URL),
  supabaseAnonKey: normalizeOptionalEnv(process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY),
};

export const hasSupabaseConfig = Boolean(frontendEnv.supabaseUrl && frontendEnv.supabaseAnonKey);
