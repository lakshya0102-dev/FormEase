'use client';

import React, { useState, useRef } from 'react';
import { UploadCloud, FileText, Trash2, ArrowRight, Clipboard, AlertCircle } from 'lucide-react';
import { api } from '@/lib/api';
import { DocumentItem } from '@/types';

interface UploadSectionProps {
  onDocumentReadyForAnalysis: (doc: DocumentItem) => Promise<void>;
}

export const UploadSection: React.FC<UploadSectionProps> = ({ onDocumentReadyForAnalysis }) => {
  const [activeTab, setActiveTab] = useState<'file' | 'paste'>('file');
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [pastedTitle, setPastedTitle] = useState('Pasted Form Content');
  const [pastedText, setPastedText] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const filesArray = Array.from(e.target.files);
      setSelectedFiles([filesArray[0]]);
      setErrorMsg(filesArray.length > 1 ? 'Choose one document at a time. You can analyze more documents separately.' : null);
      e.target.value = '';
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const filesArray = Array.from(e.dataTransfer.files);
      setSelectedFiles([filesArray[0]]);
      setErrorMsg(filesArray.length > 1 ? 'Choose one document at a time. You can analyze more documents separately.' : null);
    }
  };

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleStartAnalysis = async () => {
    setIsUploading(true);
    setErrorMsg(null);
    try {
      if (activeTab === 'file') {
        if (selectedFiles.length === 0) {
          setErrorMsg('Please select at least one document to analyze.');
          setIsUploading(false);
          return;
        }
        // Upload the primary selected document
        const targetFile = selectedFiles[0];
        const res = await api.uploadDocument(targetFile);
        await onDocumentReadyForAnalysis(res.document);
      } else {
        if (!pastedText.trim()) {
          setErrorMsg('Pasted text cannot be empty.');
          setIsUploading(false);
          return;
        }
        const res = await api.pasteDocument(pastedTitle, pastedText);
        await onDocumentReadyForAnalysis(res.document);
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to upload document.');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-slate-900 dark:text-white">New Document Analysis</h2>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Upload official forms, legal agreements, bureaucratic notices, or paste text to receive clear explanations.
        </p>
      </div>

      {/* Mode Tabs */}
      <div className="flex border-b border-slate-200 dark:border-slate-800">
        <button
          onClick={() => setActiveTab('file')}
          className={`flex items-center space-x-2 py-3 px-4 font-medium text-sm border-b-2 transition-colors ${
            activeTab === 'file'
              ? 'border-brand-500 text-brand-600 dark:text-brand-400'
              : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400'
          }`}
        >
          <UploadCloud className="w-4 h-4" />
          <span>Upload Files (PDF, DOCX, TXT)</span>
        </button>
        <button
          onClick={() => setActiveTab('paste')}
          className={`flex items-center space-x-2 py-3 px-4 font-medium text-sm border-b-2 transition-colors ${
            activeTab === 'paste'
              ? 'border-brand-500 text-brand-600 dark:text-brand-400'
              : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400'
          }`}
        >
          <Clipboard className="w-4 h-4" />
          <span>Paste Text Directly</span>
        </button>
      </div>

      {/* Error alert */}
      {errorMsg && (
        <div className="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-400 flex items-start space-x-3 text-sm">
          <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* File Dropzone Tab */}
      {activeTab === 'file' ? (
        <div className="space-y-6">
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className="border-2 border-dashed border-slate-300 dark:border-slate-700 hover:border-brand-500 dark:hover:border-brand-400 rounded-2xl p-10 text-center cursor-pointer transition-colors bg-slate-50/50 dark:bg-slate-900/50"
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept=".pdf,.docx,.txt"
              className="hidden"
            />
            <div className="w-14 h-14 mx-auto rounded-2xl bg-brand-500/10 dark:bg-brand-500/20 text-brand-600 dark:text-brand-400 flex items-center justify-center mb-4">
              <UploadCloud className="w-7 h-7" />
            </div>
            <h3 className="font-semibold text-slate-900 dark:text-white text-base">
              Drag & Drop your documents here, or <span className="text-brand-600 dark:text-brand-400">Browse files</span>
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
              Supports PDF, DOCX, TXT documents up to 18 MB.
            </p>
          </div>

          {/* Review Selected Documents Screen */}
          {selectedFiles.length > 0 && (
            <div className="space-y-3">
              <h4 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Selected Document</h4>
              <div className="divide-y divide-slate-100 dark:divide-slate-800 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
                {selectedFiles.map((file, idx) => (
                  <div key={idx} className="flex items-center justify-between p-3.5">
                    <div className="flex items-center space-x-3">
                      <FileText className="w-5 h-5 text-brand-600 dark:text-brand-400" />
                      <div>
                        <p className="font-medium text-sm text-slate-900 dark:text-white">{file.name}</p>
                        <p className="text-xs text-slate-500 dark:text-slate-400">
                          {(file.size / 1024).toFixed(1)} KB • {file.name.split('.').pop()?.toUpperCase()}
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={() => removeFile(idx)}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors"
                      title="Remove file"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        /* Pasted Text Tab */
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Document Title
            </label>
            <input
              type="text"
              value={pastedTitle}
              onChange={(e) => setPastedTitle(e.target.value)}
              className="w-full px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Document / Clause Text
            </label>
            <textarea
              rows={8}
              value={pastedText}
              onChange={(e) => setPastedText(e.target.value)}
              placeholder="Paste the complex document clauses, terms or instructions here..."
              className="w-full px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
        </div>
      )}

      {/* Explicit Start Analysis Action */}
      <div className="flex justify-end pt-4">
        <button
          onClick={handleStartAnalysis}
          disabled={isUploading || (activeTab === 'file' && selectedFiles.length === 0)}
          className="flex items-center space-x-2 px-6 py-3 rounded-xl bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white font-medium text-sm shadow-sm transition-all"
        >
          <span>{isUploading ? 'Ingesting Document...' : 'Analyze Documents'}</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};
