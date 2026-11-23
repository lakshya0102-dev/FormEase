'use client';

import React, { useState, useEffect } from 'react';
import { Sidebar, NavItem } from '@/components/layout/Sidebar';
import { Header } from '@/components/layout/Header';
import { DashboardView } from '@/components/dashboard/DashboardView';
import { UploadSection } from '@/components/upload/UploadSection';
import { AnalysisDashboard } from '@/components/viewer/AnalysisDashboard';
import { OriginalDocumentViewer } from '@/components/viewer/OriginalDocumentViewer';
import { DocumentChatbot } from '@/components/chat/DocumentChatbot';
import { DocumentLibrary } from '@/components/library/DocumentLibrary';
import { TrashView } from '@/components/trash/TrashView';
import { SettingsView } from '@/components/settings/SettingsView';
import { DocumentItem, DocumentAnalysis, DocumentChunk, SupportedLanguage, ExplanationLevel } from '@/types';
import { api, ApiError } from '@/lib/api';
import { useTheme } from '@/components/providers/ThemeProvider';
import { useAuth } from '@/components/auth/AuthProvider';

export default function Home() {
  const [activeTab, setActiveTab] = useState<NavItem>('dashboard');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const { theme, setTheme } = useTheme();
  const { user, signOut } = useAuth();
  const darkMode = theme === 'dark';

  // User Settings State
  const [language, setLanguage] = useState<SupportedLanguage>('en');
  const [depth, setDepth] = useState<ExplanationLevel>('balanced');

  // AI Connection State
  const [aiStatus, setAiStatus] = useState({
    provider: 'openrouter',
    connected: false,
    modelInstalled: false,
    modelName: 'checking configuration',
    detail: 'Checking configured AI provider...',
  });

  // Document & Viewer State
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(true);
  const [isWorking, setIsWorking] = useState(false);
  const [workflowError, setWorkflowError] = useState<string | null>(null);
  const [activeDocument, setActiveDocument] = useState<DocumentItem | null>(null);
  const [activeAnalysis, setActiveAnalysis] = useState<DocumentAnalysis | null>(null);
  const [activeChunks, setActiveChunks] = useState<DocumentChunk[]>([]);
  const [isViewingOriginal, setIsViewingOriginal] = useState(false);
  const [isChatOpen, setIsChatOpen] = useState(false);

  const loadDocuments = () => {
    setIsLoadingDocuments(true);
    api.getDocuments()
      .then((res) => setDocuments(res.documents || []))
      .catch((err) => setWorkflowError(err.message || 'Unable to load your documents.'))
      .finally(() => setIsLoadingDocuments(false));
  };

  useEffect(() => {
    const savedLanguage = window.localStorage.getItem('formease_lang');
    const savedDepth = window.localStorage.getItem('formease_depth');
    if (savedLanguage === 'en' || savedLanguage === 'hi') setLanguage(savedLanguage);
    if (savedDepth === 'simple' || savedDepth === 'balanced' || savedDepth === 'detailed') setDepth(savedDepth);
    loadDocuments();
    api.getAIStatus()
      .then((res) => {
        setAiStatus({
          provider: res.provider,
          connected: res.configured,
          modelInstalled: res.model_installed,
          modelName: res.model_name,
          detail: res.status_detail,
        });
      })
      .catch(() => {
        setAiStatus({
          provider: 'unknown',
          connected: false,
          modelInstalled: false,
          modelName: 'unavailable',
          detail: 'Cannot reach the configured AI provider.',
        });
      });
  }, []);

  const handleOpenDocument = async (doc: DocumentItem) => {
    setWorkflowError(null);
    setIsWorking(true);
    setActiveDocument(doc);
    setActiveAnalysis(null);
    setIsViewingOriginal(false);
    try {
      const res = await api.getDocument(doc.id);
      setActiveChunks(res.chunks || []);
      try {
        const aRes = await api.getAnalysis(doc.id);
        setActiveAnalysis(aRes.analysis);
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 404) throw error;
        const aRes = await api.analyzeDocument(doc.id, { language, depth });
        setActiveAnalysis(aRes.analysis);
      }
      setActiveTab('dashboard');
    } catch (error) {
      setWorkflowError(error instanceof Error ? error.message : 'Unable to open this document.');
    } finally {
      setIsWorking(false);
    }
  };

  const handleDocumentReadyForAnalysis = async (doc: DocumentItem) => {
    setWorkflowError(null);
    setIsWorking(true);
    setActiveDocument(doc);
    setActiveAnalysis(null);
    setIsViewingOriginal(false);
    try {
      const aRes = await api.analyzeDocument(doc.id, { language, depth });
      setActiveAnalysis(aRes.analysis);
      loadDocuments();
      setActiveTab('dashboard');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Document saved, but analysis could not be completed.';
      setWorkflowError(`Document saved. ${message}`);
      loadDocuments();
      throw err;
    } finally {
      setIsWorking(false);
    }
  };

  return (
    <div className="flex h-screen bg-slate-50 dark:bg-slate-950 overflow-hidden overflow-x-hidden">
      {/* Sidebar Navigation */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={(tab) => {
          setActiveTab(tab);
          if (tab !== 'dashboard') {
            setActiveDocument(null);
          }
        }}
        collapsed={sidebarCollapsed}
        setCollapsed={setSidebarCollapsed}
      />

      {/* Main Body */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Header
          darkMode={darkMode}
          setDarkMode={(value) => setTheme(value ? 'dark' : 'light')}
          accountEmail={user.email ?? 'Signed in'}
          onSignOut={() => { void signOut().catch((error) => console.error('Sign out failed:', error)); }}
          aiStatus={aiStatus}
        />

        {/* Viewport Content */}
        <main className="flex-1 min-w-0 max-w-full overflow-x-hidden overflow-y-auto p-6 md:p-8">
          {workflowError && (
            <div className="mx-auto mb-5 flex max-w-5xl items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300" role="alert">
              <span className="font-semibold">Request failed:</span>
              <span>{workflowError}</span>
              <button onClick={() => setWorkflowError(null)} className="ml-auto font-semibold underline">Dismiss</button>
            </div>
          )}
          {isWorking && (
            <div className="mx-auto mb-5 max-w-5xl rounded-xl border border-brand-200 bg-brand-50 p-4 text-sm text-brand-800 dark:border-brand-900 dark:bg-brand-950/40 dark:text-brand-300" role="status">
              Processing your document with the configured AI provider…
            </div>
          )}
          {activeTab === 'dashboard' && (
            activeDocument && activeAnalysis ? (
              isViewingOriginal ? (
                <OriginalDocumentViewer
                  document={activeDocument}
                  chunks={activeChunks}
                  onBackToAnalysis={() => setIsViewingOriginal(false)}
                />
              ) : (
                <AnalysisDashboard
                  document={activeDocument}
                  analysis={activeAnalysis}
                  onRefreshAnalysis={() => handleOpenDocument(activeDocument)}
                  onRetryAnalysis={async () => {
                    setWorkflowError(null);
                    setIsWorking(true);
                    try {
                      const retried = await api.analyzeDocument(activeDocument.id, { language, depth });
                      setActiveAnalysis(retried.analysis);
                      loadDocuments();
                    } catch (error) {
                      setWorkflowError(error instanceof Error ? error.message : 'Unable to retry the missing analysis parts.');
                    } finally {
                      setIsWorking(false);
                    }
                  }}
                  onOpenOriginal={() => setIsViewingOriginal(true)}
                  onOpenChat={() => setIsChatOpen(true)}
                />
              )
            ) : (
              <DashboardView
                documents={documents}
                isLoading={isLoadingDocuments}
                onNewAnalysis={() => setActiveTab('upload')}
                onOpenDocument={handleOpenDocument}
                onViewLibrary={() => setActiveTab('library')}
                aiProvider={aiStatus.provider}
                aiModel={aiStatus.modelName}
              />
            )
          )}

          {activeTab === 'upload' && (
            <UploadSection
              onDocumentReadyForAnalysis={handleDocumentReadyForAnalysis}
            />
          )}

          {activeTab === 'library' && (
            <DocumentLibrary
              documents={documents}
              onOpenDocument={handleOpenDocument}
              onRefresh={loadDocuments}
            />
          )}

          {activeTab === 'trash' && <TrashView onRestored={loadDocuments} />}

          {activeTab === 'settings' && (
            <SettingsView
              language={language}
              setLanguage={setLanguage}
              depth={depth}
              setDepth={setDepth}
              aiStatus={aiStatus}
            />
          )}

          {activeTab === 'profile' && (
            <div className="max-w-xl mx-auto bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">Account Profile</h2>
              <div className="space-y-2 text-xs text-slate-600 dark:text-slate-300">
                <p><span className="font-semibold">User:</span> {user.email || user.id}</p>
                <p><span className="font-semibold">Authentication:</span> Supabase Auth (Email / Password)</p>
                <p><span className="font-semibold">Role:</span> Authenticated Member</p>
                <p><span className="font-semibold">Storage:</span> Supabase Private Storage Bucket</p>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Grounded Document Chatbot Floating Drawer */}
      {isChatOpen && activeDocument && (
        <DocumentChatbot
          document={activeDocument}
          onClose={() => setIsChatOpen(false)}
        />
      )}
    </div>
  );
}
