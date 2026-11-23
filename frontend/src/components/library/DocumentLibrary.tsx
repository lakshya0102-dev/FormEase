'use client';

import React, { useState } from 'react';
import { Search, FolderArchive, FileText, Trash2, ArrowUpRight, ArrowUpDown } from 'lucide-react';
import { DocumentItem } from '@/types';
import { api } from '@/lib/api';

interface DocumentLibraryProps {
  documents: DocumentItem[];
  onOpenDocument: (doc: DocumentItem) => void;
  onRefresh: () => void;
}

export const DocumentLibrary: React.FC<DocumentLibraryProps> = ({
  documents,
  onOpenDocument,
  onRefresh,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [sortBy, setSortBy] = useState<'date' | 'name'>('date');
  const [errorMessage, setErrorMessage] = useState('');
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const filteredDocs = documents
    .filter((d) => d.title.toLowerCase().includes(searchTerm.toLowerCase()))
    .sort((a, b) => {
      if (sortBy === 'name') {
        return a.title.localeCompare(b.title);
      }
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (confirm('Move this document to Recently Deleted?')) {
      setDeletingId(id);
      setErrorMessage('');
      try {
        await api.deleteDocument(id);
        onRefresh();
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : 'Could not move this document to Recently Deleted.');
      } finally {
        setDeletingId(null);
      }
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Document Library</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Access your simplified documents, summaries, and saved conversations.
          </p>
        </div>

        {/* Search & Sort Controls */}
        <div className="flex items-center space-x-3">
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search by filename..."
              className="pl-9 pr-4 py-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-xs text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500 w-52"
            />
          </div>
          <button
            onClick={() => setSortBy(sortBy === 'date' ? 'name' : 'date')}
            className="flex items-center space-x-1.5 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-xs text-slate-600 dark:text-slate-300 hover:bg-slate-50"
            title="Toggle sort by date / name"
          >
            <ArrowUpDown className="w-3.5 h-3.5" />
            <span>{sortBy === 'date' ? 'Date' : 'Name'}</span>
          </button>
        </div>
      </div>

      {errorMessage && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300" role="alert">{errorMessage}</div>}

      {filteredDocs.length === 0 ? (
        <div className="text-center py-16 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6">
          <FolderArchive className="w-10 h-10 text-slate-300 dark:text-slate-600 mx-auto mb-3" />
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">No documents found</h3>
          <p className="text-xs text-slate-500 mt-1">
            {searchTerm ? 'Try a different search term.' : 'Upload your first document to get started.'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredDocs.map((doc) => (
            <div
              key={doc.id}
              onClick={() => onOpenDocument(doc)}
              className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:border-brand-500 dark:hover:border-brand-500/80 rounded-2xl p-5 shadow-sm hover:shadow-md cursor-pointer transition-all flex flex-col justify-between group space-y-4"
            >
              <div className="space-y-3">
                <div className="flex items-start justify-between">
                  <div className="p-2 rounded-xl bg-brand-500/10 text-brand-600 dark:text-brand-400">
                    <FileText className="w-5 h-5" />
                  </div>
                  <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500">
                    {doc.file_type}
                  </span>
                </div>
                <div>
                  <h3 className="font-semibold text-sm text-slate-900 dark:text-white line-clamp-2 group-hover:text-brand-600 dark:group-hover:text-brand-400 transition-colors">
                    {doc.title}
                  </h3>
                  <p className="text-xs text-slate-400 mt-1">
                    {new Date(doc.created_at).toLocaleDateString()} • {doc.page_count} Pages
                  </p>
                </div>
              </div>

              <div className="flex items-center justify-between pt-3 border-t border-slate-100 dark:border-slate-800 text-xs">
                <span className="flex items-center text-brand-600 dark:text-brand-400 font-medium">
                  <span>Open Analysis</span>
                  <ArrowUpRight className="w-3.5 h-3.5 ml-0.5" />
                </span>
                <button
                  onClick={(e) => handleDelete(e, doc.id)}
                  disabled={deletingId === doc.id}
                  className="p-1 rounded-lg text-slate-400 hover:text-rose-600 transition-colors disabled:opacity-50"
                  title="Move to trash"
                >
                  {deletingId === doc.id ? <span className="text-[10px]">Moving…</span> : <Trash2 className="w-4 h-4" />}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
