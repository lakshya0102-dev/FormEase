import { frontendEnv } from '@/lib/env';
import { supabase } from '@/lib/supabase';

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function authorizedFetch(endpoint: string, options: RequestInit = {}) {
  const sessionResult = supabase ? await supabase.auth.getSession() : null;
  if (sessionResult?.error) throw sessionResult.error;
  const headers = new Headers(options.headers || {});
  const initialToken = sessionResult?.data.session?.access_token;

  const url = `${frontendEnv.apiUrl}${endpoint}`;
  const send = () => fetch(url, { ...options, headers });
  if (initialToken) headers.set('Authorization', `Bearer ${initialToken}`);
  let response = await send();

  if (response.status === 401 && initialToken && supabase) {
    const refreshed = await supabase.auth.refreshSession();
    const newToken = refreshed.data.session?.access_token;
    if (refreshed.error || !newToken) {
      await supabase.auth.signOut({ scope: 'local' }).catch(() => undefined);
    } else if (newToken !== initialToken) {
      headers.set('Authorization', `Bearer ${newToken}`);
      response = await send();
    }
  }
  return response;
}

async function throwApiError(response: Response): Promise<never> {
  const errorData = await response.json().catch(() => ({}));
  throw new ApiError(errorData.detail || errorData.message || `HTTP error ${response.status}`, response.status);
}

export async function fetchWithAuth(endpoint: string, options: RequestInit = {}) {
  const res = await authorizedFetch(endpoint, options);
  if (!res.ok) {
    await throwApiError(res);
  }

  if (res.status === 204) return undefined;
  return res.json();
}

async function downloadWithAuth(endpoint: string) {
  const response = await authorizedFetch(endpoint);
  if (!response.ok) {
    await throwApiError(response);
  }

  return response.blob();
}

export const api = {
  getHealth: () => fetchWithAuth('/health'),
  getAIStatus: () => fetchWithAuth('/ai/status'),
  
  // Documents
  getDocuments: () => fetchWithAuth('/documents'),
  getTrash: () => fetchWithAuth('/documents/trash'),
  getDocument: (id: string) => fetchWithAuth(`/documents/${id}`),
  getDocumentContent: (id: string) => downloadWithAuth(`/documents/${id}/content`),
  deleteDocument: (id: string) => fetchWithAuth(`/documents/${id}`, { method: 'DELETE' }),
  restoreDocument: (id: string) => fetchWithAuth(`/documents/${id}/restore`, { method: 'POST' }),
  
  uploadDocument: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return fetchWithAuth('/documents/upload', {
      method: 'POST',
      body: formData,
    });
  },

  pasteDocument: async (title: string, text: string) => {
    const formData = new FormData();
    formData.append('title', title);
    formData.append('text', text);
    return fetchWithAuth('/documents/paste', {
      method: 'POST',
      body: formData,
    });
  },

  // Analysis
  analyzeDocument: (documentId: string, options: { language: string; depth: string; components?: string[] }) =>
    fetchWithAuth(`/documents/${documentId}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(options),
    }),

  getAnalysis: (documentId: string) => fetchWithAuth(`/documents/${documentId}/analysis`),

  refineComponent: (componentId: string, instruction: string) =>
    fetchWithAuth(`/analysis/${componentId}/regenerate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instruction }),
    }),

  // Chat
  askQuestion: (documentId: string, question: string) =>
    fetchWithAuth(`/documents/${documentId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    }),

  getConversations: (documentId: string) => fetchWithAuth(`/documents/${documentId}/conversations`),
  submitFeedback: (messageId: string, payload: { is_positive: boolean; comment?: string }) =>
    fetchWithAuth(`/messages/${messageId}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  // Annotations
  getAnnotations: (documentId: string) => fetchWithAuth(`/documents/${documentId}/annotations`),
  addAnnotation: (documentId: string, payload: { note: string; highlighted_text?: string; page_number?: number; color?: string }) =>
    fetchWithAuth(`/documents/${documentId}/annotations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  deleteAnnotation: (annotationId: string) => fetchWithAuth(`/annotations/${annotationId}`, { method: 'DELETE' }),

  // Export
  getExportMarkdown: (documentId: string) => fetchWithAuth(`/documents/${documentId}/export/markdown`),
  downloadExportPdf: (documentId: string) => downloadWithAuth(`/documents/${documentId}/export/pdf`),
};
