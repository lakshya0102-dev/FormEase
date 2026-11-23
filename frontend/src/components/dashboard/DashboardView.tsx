'use client';

import React from 'react';
import { FilePlus2, Sparkles, Clock } from 'lucide-react';
import { DocumentItem } from '@/types';

interface DashboardViewProps {
  documents: DocumentItem[];
  isLoading?: boolean;
  onNewAnalysis: () => void;
  onOpenDocument: (doc: DocumentItem) => void;
  onViewLibrary: () => void;
  aiProvider: string;
  aiModel: string;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  documents,
  isLoading = false,
  onNewAnalysis,
  onOpenDocument,
  onViewLibrary,
  aiProvider,
  aiModel,
}) => {
  const recentDocs = documents.slice(0, 5);
  const providerLabel = aiProvider === 'openrouter' ? 'OpenRouter' : aiProvider;

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      {/* Welcome Banner */}
      <div className="bg-gradient-to-r from-brand-600 to-teal-700 rounded-3xl p-8 text-white shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
        <div className="space-y-2 max-w-xl">
          <div className="flex items-center space-x-2 text-brand-100 text-xs font-semibold uppercase tracking-wider">
            <Sparkles className="w-4 h-4" />
            <span>AI Document Simplification</span>
          </div>
          <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight">
            Make complex documents simple and actionable.
          </h1>
          <p className="text-brand-100/90 text-xs md:text-sm leading-relaxed">
            Upload PDF, DOCX, TXT files or paste legal clauses to extract plain summaries, workflow steps, deadlines, definitions and ask grounded questions.
          </p>
        </div>
        <button
          onClick={onNewAnalysis}
          className="flex items-center space-x-2 px-5 py-3 rounded-2xl bg-white text-brand-700 hover:bg-brand-50 font-bold text-xs shadow-md transition-all flex-shrink-0"
        >
          <FilePlus2 className="w-4 h-4" />
          <span>New Analysis</span>
        </button>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm space-y-1">
          <span className="text-xs font-medium text-slate-400">Saved Documents</span>
          <p className="text-2xl font-bold text-slate-900 dark:text-white">{documents.length}</p>
        </div>
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm space-y-1">
          <span className="text-xs font-medium text-slate-400">Configured AI Provider</span>
          <p className="text-sm font-semibold text-slate-700 dark:text-slate-300 mt-1">
            {providerLabel} · {aiModel}
          </p>
        </div>
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm space-y-1">
          <span className="text-xs font-medium text-slate-400">Supported Formats</span>
          <p className="text-sm font-semibold text-slate-700 dark:text-slate-300 mt-1">
            PDF, DOCX, TXT, Pasted Text
          </p>
        </div>
      </div>

      {/* Recent Documents Table */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Clock className="w-4 h-4 text-brand-600" />
            <h3 className="font-bold text-sm text-slate-900 dark:text-white">Recent Documents</h3>
          </div>
          <button
            onClick={onViewLibrary}
            className="text-xs text-brand-600 dark:text-brand-400 font-semibold hover:underline"
          >
            View all library
          </button>
        </div>

        {isLoading ? (
          <div className="py-12 text-center text-xs text-slate-400" role="status">Loading your saved documents…</div>
        ) : recentDocs.length === 0 ? (
          <div className="text-center py-12 text-slate-400 text-xs">
            No documents analyzed yet. Click &ldquo;New Analysis&rdquo; to begin.
          </div>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {recentDocs.map((doc) => (
              <div
                key={doc.id}
                onClick={() => onOpenDocument(doc)}
                className="py-3 flex items-center justify-between hover:bg-slate-50/80 dark:hover:bg-slate-800/40 px-2 rounded-xl cursor-pointer transition-colors"
              >
                <div>
                  <h4 className="text-xs font-semibold text-slate-800 dark:text-slate-200">{doc.title}</h4>
                  <p className="text-[11px] text-slate-400">
                    {new Date(doc.created_at).toLocaleDateString()} • {doc.page_count} Pages • {doc.file_type.toUpperCase()}
                  </p>
                </div>
                <span className="text-xs font-semibold text-brand-600 dark:text-brand-400">
                  Open &rarr;
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
