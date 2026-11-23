'use client';

import React, { FormEvent, useEffect, useState } from 'react';
import { ArrowLeft, FileText, MessageSquarePlus, Trash2 } from 'lucide-react';
import { Annotation, DocumentItem } from '@/types';
import { api } from '@/lib/api';

function renderAnnotatedText(content: string, pageNumber: number, annotations: Annotation[]) {
  const phrases = annotations
    .filter((annotation) => annotation.page_number === pageNumber && annotation.highlighted_text?.trim())
    .map((annotation) => annotation.highlighted_text!.trim())
    .sort((a, b) => b.length - a.length);
  if (phrases.length === 0) return content;

  const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const matcher = new RegExp(`(${phrases.map(escapeRegExp).join('|')})`, 'gi');
  return content.split(matcher).map((part, index) => (
    phrases.some((phrase) => phrase.toLocaleLowerCase() === part.toLocaleLowerCase())
      ? <mark key={`${pageNumber}-${index}`} className="rounded bg-amber-200 px-0.5 text-inherit dark:bg-amber-800/70">{part}</mark>
      : part
  ));
}

interface OriginalDocumentViewerProps {
  document: DocumentItem;
  chunks: Array<{ chunk_index: number; content: string; page_number: number; section_title: string }>;
  onBackToAnalysis: () => void;
}

export const OriginalDocumentViewer: React.FC<OriginalDocumentViewerProps> = ({
  document,
  chunks,
  onBackToAnalysis,
}) => {
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [note, setNote] = useState('');
  const [highlightedText, setHighlightedText] = useState('');
  const [pageNumber, setPageNumber] = useState(1);
  const [errorMessage, setErrorMessage] = useState('');
  const [originalPdfUrl, setOriginalPdfUrl] = useState('');

  useEffect(() => {
    let objectUrl = '';
    let isMounted = true;
    setOriginalPdfUrl('');
    setErrorMessage('');
    if (document.file_type === 'pdf') {
      api.getDocumentContent(document.id)
        .then((file) => {
          const fileUrl = URL.createObjectURL(file);
          if (isMounted) {
            objectUrl = fileUrl;
            setOriginalPdfUrl(fileUrl);
          } else {
            URL.revokeObjectURL(fileUrl);
          }
        })
        .catch((error) => setErrorMessage(error.message || 'Could not load the original PDF.'));
    }
    api.getAnnotations(document.id)
      .then((response) => setAnnotations(response.annotations || []))
      .catch((error) => setErrorMessage(error.message || 'Could not load annotations.'));
    return () => {
      isMounted = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [document.id, document.file_type]);

  const useSelection = () => {
    const selection = window.getSelection()?.toString().trim();
    if (selection) setHighlightedText(selection);
  };

  const addAnnotation = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!note.trim()) return;
    try {
      setErrorMessage('');
      const created = await api.addAnnotation(document.id, {
        note: note.trim(),
        highlighted_text: highlightedText.trim() || undefined,
        page_number: pageNumber,
      });
      setAnnotations((current) => [...current, created]);
      setNote('');
      setHighlightedText('');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Could not save your annotation.');
    }
  };

  const deleteAnnotation = async (id: string) => {
    try {
      setErrorMessage('');
      await api.deleteAnnotation(id);
      setAnnotations((current) => current.filter((annotation) => annotation.id !== id));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Could not delete this annotation.');
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Top Bar */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-200 dark:border-slate-800">
        <button
          onClick={onBackToAnalysis}
          className="flex items-center space-x-2 text-xs font-semibold text-brand-600 dark:text-brand-400 hover:underline"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Analysis Dashboard</span>
        </button>
        <span className="text-xs text-slate-500">Original Document Content</span>
      </div>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex items-center space-x-3">
          <FileText className="w-6 h-6 text-brand-600" />
          <div>
            <h2 className="text-lg font-bold text-slate-900 dark:text-white">{document.title}</h2>
            <p className="text-xs text-slate-500">
              Format: {document.file_type.toUpperCase()} • {chunks.length} Extracted Text Chunks
            </p>
          </div>
        </div>

        {/* Chunks rendering preserving page markers */}
        <div className="space-y-4 pt-4 divide-y divide-slate-100 dark:divide-slate-800">
          {chunks.map((chunk, idx) => (
            <div key={idx} className="pt-4 first:pt-0 space-y-2">
              <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                <span>{chunk.section_title || 'Section'}</span>
                <span>Page {chunk.page_number}</span>
              </div>
              <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed font-sans whitespace-pre-line">
                {renderAnnotatedText(chunk.content, chunk.page_number, annotations)}
              </p>
            </div>
          ))}
        </div>
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-bold text-slate-900 dark:text-white">
          <MessageSquarePlus className="h-4 w-4 text-brand-600" /> Notes & Annotations
        </h3>
        {errorMessage && <p className="mb-3 rounded-lg bg-rose-50 p-3 text-xs text-rose-700 dark:bg-rose-950/40 dark:text-rose-300" role="alert">{errorMessage}</p>}
        <form onSubmit={addAnnotation} className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor="annotation-page" className="text-xs text-slate-500">Page</label>
            <select id="annotation-page" value={pageNumber} onChange={(event) => setPageNumber(Number(event.target.value))} className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-950">
              {Array.from(new Set(chunks.map((chunk) => chunk.page_number))).sort((a, b) => a - b).map((page) => <option key={page} value={page}>{page}</option>)}
            </select>
            <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={useSelection} className="text-xs font-medium text-brand-700 hover:underline dark:text-brand-400">Use selected document text</button>
          </div>
          <textarea value={highlightedText} onChange={(event) => setHighlightedText(event.target.value)} rows={2} placeholder="Optional highlighted text" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-950" />
          <div className="flex gap-2">
            <input value={note} onChange={(event) => setNote(event.target.value)} required placeholder="Write a personal note about this page" className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-950" />
            <button type="submit" disabled={!note.trim()} className="rounded-xl bg-brand-600 px-4 py-2 text-xs font-semibold text-white hover:bg-brand-700 disabled:opacity-50">Save note</button>
          </div>
        </form>

        <div className="mt-5 space-y-2">
          {annotations.map((annotation) => (
            <article key={annotation.id} className="rounded-xl border border-slate-100 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-800/50">
              <div className="mb-1 flex items-center justify-between text-[11px] text-slate-500">
                <span>Page {annotation.page_number}</span>
                <button type="button" onClick={() => deleteAnnotation(annotation.id)} aria-label="Delete annotation" className="rounded p-1 text-slate-400 hover:text-rose-600"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
              {annotation.highlighted_text && <p className="mb-2 border-l-2 border-amber-400 pl-2 text-xs italic text-slate-600 dark:text-slate-300">{annotation.highlighted_text}</p>}
              <p className="whitespace-pre-wrap text-xs text-slate-800 dark:text-slate-200">{annotation.note}</p>
            </article>
          ))}
          {annotations.length === 0 && <p className="text-xs text-slate-400">No notes saved for this document yet.</p>}
        </div>
      </section>

      {document.file_type === 'pdf' && (
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <h3 className="border-b border-slate-200 px-5 py-3 text-sm font-semibold text-slate-900 dark:border-slate-800 dark:text-white">Original PDF</h3>
          {originalPdfUrl ? (
            <iframe title={`Original PDF: ${document.title}`} src={originalPdfUrl} className="h-[70vh] w-full bg-white" />
          ) : <p className="p-5 text-xs text-slate-500" role="status">Loading original PDF…</p>}
        </section>
      )}
    </div>
  );
};
