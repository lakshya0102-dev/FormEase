'use client';

import React, { useState, useEffect } from 'react';
import { Trash2, RotateCcw, FileText } from 'lucide-react';
import { DocumentItem } from '@/types';
import { api } from '@/lib/api';

export const TrashView: React.FC<{ onRestored?: () => void }> = ({ onRestored }) => {
  const [trashDocs, setTrashDocs] = useState<DocumentItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState('');
  const [restoringId, setRestoringId] = useState<string | null>(null);

  const loadTrash = () => {
    setIsLoading(true);
    setErrorMessage('');
    api.getTrash()
      .then((res) => setTrashDocs(res.documents || []))
      .catch((err) => setErrorMessage(err instanceof Error ? err.message : 'Could not load recently deleted documents.'))
      .finally(() => setIsLoading(false));
  };

  useEffect(() => {
    loadTrash();
  }, []);

  const handleRestore = async (id: string) => {
    setRestoringId(id);
    setErrorMessage('');
    try {
      await api.restoreDocument(id);
      onRestored?.();
      loadTrash();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Could not restore this document.');
    } finally {
      setRestoringId(null);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Recently Deleted</h2>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Restore a document to return it to your library.
        </p>
      </div>

      {isLoading ? (
        <p className="py-12 text-center text-xs text-slate-400" role="status">Loading recently deleted documents…</p>
      ) : errorMessage ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300" role="alert">{errorMessage}</div>
      ) : trashDocs.length === 0 ? (
        <div className="text-center py-16 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6">
          <Trash2 className="w-10 h-10 text-slate-300 dark:text-slate-600 mx-auto mb-3" />
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">Trash is empty</h3>
          <p className="text-xs text-slate-500 mt-1">No recently deleted documents.</p>
        </div>
      ) : (
        <div className="divide-y divide-slate-100 dark:divide-slate-800 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden shadow-sm">
          {trashDocs.map((doc) => (
            <div key={doc.id} className="p-4 flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <FileText className="w-5 h-5 text-slate-400" />
                <div>
                  <h4 className="text-sm font-semibold text-slate-800 dark:text-slate-200">{doc.title}</h4>
                  <p className="text-xs text-slate-400">
                    Deleted on: {doc.deleted_at ? new Date(doc.deleted_at).toLocaleDateString() : 'Recently'}
                  </p>
                </div>
              </div>
              <button
                onClick={() => handleRestore(doc.id)}
                disabled={restoringId === doc.id}
                className="flex items-center space-x-1 px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>{restoringId === doc.id ? 'Restoring…' : 'Restore'}</span>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
