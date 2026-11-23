'use client';

import React, { useCallback, useState } from 'react';
import { 
  FileText, 
  Sparkles, 
  GitBranch, 
  AlertTriangle, 
  BookOpen, 
  Lightbulb, 
  ShieldCheck, 
  Download, 
  Copy, 
  RotateCcw,
  Check,
  Layers,
  FileCode,
  NotebookPen
} from 'lucide-react';
import { DocumentItem, DocumentAnalysis, ProcessStep } from '@/types';
import { api } from '@/lib/api';
import { MermaidDiagram } from '@/components/viewer/MermaidDiagram';

interface AnalysisDashboardProps {
  document: DocumentItem;
  analysis: DocumentAnalysis;
  onRefreshAnalysis: () => void | Promise<void>;
  onRetryAnalysis: () => void;
  onOpenOriginal: () => void;
  onOpenChat: () => void;
}

function buildProcessDiagramFromSteps(steps: DocumentAnalysis['process_flow']['steps']): string {
  const validSteps = steps.filter((step) => step.title?.trim() && step.description?.trim());
  if (!validSteps.length) return '';
  const label = (value: string) => value.replace(/[\[\]{}<>"'`|\\\n\r]/g, ' ').trim().slice(0, 90);
  const ids = new Map(validSteps.map((step, index) => [step.title.toLocaleLowerCase(), `S${index + 1}`]));
  const lines = ['flowchart TD'];
  validSteps.forEach((step, index) => {
    const id = `S${index + 1}`;
    const text = label(step.condition ? `${step.title}: ${step.condition}` : step.title);
    if (step.node_type === 'decision') lines.push(`  ${id}{"${text}"}`);
    else if (step.node_type === 'start' || step.node_type === 'end') lines.push(`  ${id}(["${text}"])`);
    else lines.push(`  ${id}["${text}"]`);
  });
  validSteps.forEach((step, index) => {
    const from = `S${index + 1}`;
    const explicit = (step.next_steps || []).flatMap((next) => {
      const target = ids.get(next.title.toLocaleLowerCase());
      return target ? [{ target, condition: next.condition }] : [];
    });
    if (explicit.length) {
      explicit.forEach((next) => {
        const condition = next.condition ? label(next.condition) : '';
        lines.push(condition ? `  ${from} -->|${condition}| ${next.target}` : `  ${from} --> ${next.target}`);
      });
    } else if (index < validSteps.length - 1) {
      lines.push(`  ${from} --> S${index + 2}`);
    }
  });
  return lines.join('\n');
}

function ProcessStepDetails({
  step,
  index,
  total,
  previousStep,
  nextStep,
  onSelectStep,
}: {
  step: ProcessStep;
  index: number;
  total: number;
  previousStep?: ProcessStep;
  nextStep?: ProcessStep;
  onSelectStep: (stepIndex: number) => void;
}) {
  const inputs = step.inputs_outputs?.inputs ?? step.inputs ?? [];
  const outputs = step.inputs_outputs?.outputs ?? step.outputs ?? [];
  const explanation = step.brief_explanation?.trim()
    || step.summary?.trim()
    || step.description?.trim()
    || 'Step details are unavailable in this saved analysis.';

  return (
    <article
      className="min-w-0 max-w-full break-words rounded-xl border border-brand-200 p-4 dark:border-brand-800 [&_h3]:max-w-full [&_h3]:break-words [&_h3]:whitespace-normal [&_h4]:max-w-full [&_h4]:break-words [&_h4]:whitespace-normal [&_li]:max-w-full [&_li]:break-words [&_li]:whitespace-normal [&_p]:max-w-full [&_p]:break-words [&_p]:whitespace-normal"
      aria-live="polite"
    >
      <header className="flex min-w-0 max-w-full flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 max-w-full">
          <span className="inline-flex rounded-full bg-brand-50 px-2.5 py-1 text-xs font-semibold text-brand-700 dark:bg-brand-900/40 dark:text-brand-200">
            Step {index + 1} of {total}
          </span>
          <h3 className="mt-2 text-lg font-semibold">{step.title}</h3>
        </div>
        <span className="max-w-full break-words rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {step.page_number ? `Source · Page ${step.page_number}` : 'Source page not identified'}
        </span>
      </header>

      <div className="mt-4 grid min-w-0 max-w-full gap-4">
        <section>
          <h4 className="text-sm font-semibold">What Happens in This Step</h4>
          <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-300">{explanation}</p>
        </section>

        <section>
          <h4 className="text-sm font-semibold">Key Actions &amp; Operations</h4>
          {step.key_actions?.length ? (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600 dark:text-slate-300">
              {step.key_actions.map((action, actionIndex) => <li key={actionIndex}>{action}</li>)}
            </ul>
          ) : <p className="mt-1 text-sm text-slate-500">No detailed actions are available in this saved analysis.</p>}
        </section>

        <section>
          <h4 className="text-sm font-semibold">Inputs → Outputs</h4>
          <div className="mt-2 grid min-w-0 max-w-full gap-3 sm:grid-cols-2">
            <div className="min-w-0 rounded-lg bg-slate-50 p-3 dark:bg-slate-800/70">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Inputs</p>
              <p className="mt-1 text-sm text-slate-700 dark:text-slate-300">
                {inputs.length ? inputs.join(', ') : 'Not identified in this saved analysis.'}
              </p>
            </div>
            <div className="min-w-0 rounded-lg bg-slate-50 p-3 dark:bg-slate-800/70">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Outputs</p>
              <p className="mt-1 text-sm text-slate-700 dark:text-slate-300">
                {outputs.length ? outputs.join(', ') : 'Not identified in this saved analysis.'}
              </p>
            </div>
          </div>
        </section>

        <section>
          <h4 className="text-sm font-semibold">Involved Components / Protocols</h4>
          {step.key_components_or_actors?.length ? (
            <div className="mt-2 flex min-w-0 max-w-full flex-wrap gap-2">
              {step.key_components_or_actors.map((component, componentIndex) => (
                <span key={componentIndex} className="max-w-full break-words rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                  {component}
                </span>
              ))}
            </div>
          ) : <p className="mt-1 text-sm text-slate-500">No components or actors were identified in this saved analysis.</p>}
        </section>

        <section className="border-t border-slate-200 pt-3 dark:border-slate-700">
          <h4 className="text-sm font-semibold">Flow Navigation</h4>
          <div className="mt-2 grid min-w-0 max-w-full gap-2 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_auto_minmax(0,1fr)] sm:items-center">
            <div className="min-w-0 rounded-lg bg-slate-50 p-2 dark:bg-slate-800/70">
              <p className="text-[11px] font-semibold uppercase text-slate-500">Previous Step</p>
              <p className="mt-1 text-sm">{previousStep?.title || 'Start of process'}</p>
            </div>
            <span className="hidden text-slate-400 sm:inline" aria-hidden="true">→</span>
            <div className="min-w-0 rounded-lg border border-brand-200 bg-brand-50 p-2 dark:border-brand-800 dark:bg-brand-900/20">
              <p className="text-[11px] font-semibold uppercase text-brand-700 dark:text-brand-300">Current Step</p>
              <p className="mt-1 text-sm font-medium">{step.title}</p>
            </div>
            <span className="hidden text-slate-400 sm:inline" aria-hidden="true">→</span>
            <div className="min-w-0 rounded-lg bg-slate-50 p-2 dark:bg-slate-800/70">
              <p className="text-[11px] font-semibold uppercase text-slate-500">Next Step</p>
              <p className="mt-1 text-sm">{nextStep?.title || 'End of process'}</p>
            </div>
          </div>
          <div className="mt-3 flex gap-2">
            <button type="button" disabled={!previousStep} onClick={() => onSelectStep(index - 1)}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium disabled:opacity-40 dark:border-slate-700">
              Previous
            </button>
            <button type="button" disabled={!nextStep} onClick={() => onSelectStep(index + 1)}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium disabled:opacity-40 dark:border-slate-700">
              Next
            </button>
          </div>
        </section>
      </div>
    </article>
  );
}

export const AnalysisDashboard: React.FC<AnalysisDashboardProps> = ({
  document,
  analysis,
  onRefreshAnalysis,
  onRetryAnalysis,
  onOpenOriginal,
  onOpenChat,
}) => {
  const [activeSection, setActiveSection] = useState('overview');
  const [processView, setProcessView] = useState<'flowchart' | 'timeline'>('flowchart');
  const [selectedStepIndex, setSelectedStepIndex] = useState(0);
  const [copied, setCopied] = useState(false);
  const [refiningComponent, setRefiningComponent] = useState<string | null>(null);
  const [refineInstruction, setRefineInstruction] = useState('');
  const [isRefining, setIsRefining] = useState(false);
  const [actionError, setActionError] = useState('');
  const [selectedConcept, setSelectedConcept] = useState<number | null>(null);
  const [isReanalyzingConceptMap, setIsReanalyzingConceptMap] = useState(false);
  const analysisIncomplete = analysis.reliability_report?.is_complete === false;
  const analysisFailure = analysis.reliability_report?.warnings?.find((warning) => warning.toLowerCase().includes('failed'));
  const moduleNeedsRetry = (module: string) => analysis.reliability_report?.failed_modules?.some((item) => item.startsWith(`${module}:`)) ?? false;
  const savedSections = (analysis.sections || []).filter((section) => {
    const heading = (section.heading || '').trim();
    const explanation = (section.simplified_explanation || '').trim();
    const placeholder = /^(this section provides an overview|this section provides a concise summary|this section explains each section|a concise summary of this part|plain explanation of)/i;
    return Boolean(heading) && !placeholder.test(heading) && Boolean(explanation) && !placeholder.test(explanation);
  });
  const processDiagram = analysis.process_flow.mermaid_syntax || buildProcessDiagramFromSteps(analysis.process_flow.steps || []);
  const processSteps = analysis.process_flow.steps || [];
  const selectedProcessStep = processSteps[selectedStepIndex];
  const handleProcessDiagramNodeClick = useCallback((nodeId: string) => {
    const match = nodeId.match(/^S(\d+)$/i);
    if (!match) return;
    const index = Number(match[1]) - 1;
    if (index >= 0 && index < processSteps.length) setSelectedStepIndex(index);
  }, [processSteps.length]);
  const conceptMapNeedsRefresh = (analysis.concept_map?.concepts || []).some((concept) =>
    !concept.key_responsibilities?.length
    || !concept.protocols_hardware_standards?.length
    || !concept.data_unit?.trim()
  );

  const handleCopyMarkdown = async () => {
    try {
      setActionError('');
      const res = await api.getExportMarkdown(document.id);
      await navigator.clipboard.writeText(res.markdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to copy the analysis.');
    }
  };

  const handleDownloadPdf = async () => {
    try {
      setActionError('');
      const pdf = await api.downloadExportPdf(document.id);
      const url = URL.createObjectURL(pdf);
      const link = window.document.createElement('a');
      link.href = url;
      link.download = `FormEase_Analysis_${document.title.replace(/[\\/]/g, '_')}.pdf`;
      window.document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to download the PDF.');
    }
  };

  const handleRefine = async () => {
    if (!refiningComponent || !refineInstruction.trim()) return;
    const componentId = analysis.component_ids?.[refiningComponent];
    if (!componentId) {
      setActionError('This analysis component is not available for regeneration.');
      return;
    }
    setIsRefining(true);
    try {
      setActionError('');
      await api.refineComponent(componentId, refineInstruction);
      setRefiningComponent(null);
      setRefineInstruction('');
      onRefreshAnalysis();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Unable to regenerate this component.');
    } finally {
      setIsRefining(false);
    }
  };

  const handleReanalyzeConceptMap = async () => {
    setIsReanalyzingConceptMap(true);
    try {
      setActionError('');
      await api.analyzeDocument(document.id, {
        language: analysis.language,
        depth: analysis.depth,
        components: ['concept_map'],
      });
      await onRefreshAnalysis();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Unable to re-analyze the Concept Map.');
    } finally {
      setIsReanalyzingConceptMap(false);
    }
  };

  const navItems = [
    { id: 'overview', label: '1. Overview', icon: FileText },
    { id: 'summary', label: '2. Summary', icon: Sparkles },
    { id: 'sections', label: '3. Section Explorer', icon: Layers },
    { id: 'process', label: '4. Process & Flow', icon: GitBranch },
    { id: 'concept_map', label: '5. Concept Map', icon: GitBranch },
    { id: 'revision', label: '6. Revision Notes & Formulas', icon: NotebookPen },
    { id: 'key_info', label: '7. Key Information', icon: AlertTriangle },
    { id: 'definitions', label: '8. Definitions & Glossary', icon: BookOpen },
    { id: 'recommendations', label: '9. Recommendations', icon: Lightbulb },
    { id: 'reliability', label: '10. Reliability & Coverage', icon: ShieldCheck },
  ];

  return (
    <div className="mx-auto flex w-full min-w-0 max-w-7xl flex-col gap-6 overflow-x-hidden lg:flex-row">
      {/* Left Column: Interactive Table of Contents */}
      <div className="lg:w-64 flex-shrink-0">
        <div className="sticky top-24 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 space-y-4 shadow-sm">
          <div className="border-b border-slate-100 dark:border-slate-800 pb-3">
            <h3 className="font-bold text-slate-900 dark:text-white text-sm">Table of Contents</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 truncate">{document.title}</p>
          </div>

          <nav className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeSection === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveSection(item.id)}
                  className={`w-full flex items-center space-x-2.5 px-3 py-2 rounded-xl text-xs font-medium transition-colors ${
                    isActive
                      ? 'bg-brand-50 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300'
                      : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800'
                  }`}
                >
                  <Icon className="w-4 h-4 flex-shrink-0" />
                  <span className="truncate">{item.label}</span>
                </button>
              );
            })}
          </nav>

          {/* Quick Actions */}
          <div className="border-t border-slate-100 dark:border-slate-800 pt-3 space-y-2">
            <button
              onClick={onOpenOriginal}
              className="w-full flex items-center justify-center space-x-2 py-2 px-3 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
            >
              <FileCode className="w-3.5 h-3.5" />
              <span>Original Document</span>
            </button>
            <button
              onClick={onOpenChat}
              className="w-full flex items-center justify-center space-x-2 py-2 px-3 rounded-xl bg-brand-600 hover:bg-brand-700 text-white text-xs font-medium shadow-sm transition-colors"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Ask Document Chatbot</span>
            </button>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 min-w-0 max-w-full space-y-6">
        {actionError && (
          <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300" role="alert">
            {actionError}
          </div>
        )}
        {/* Top Bar: Title & Export Actions */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2">
              <span className="px-2.5 py-0.5 rounded-full bg-brand-50 dark:bg-brand-900/30 text-brand-600 dark:text-brand-400 text-xs font-semibold uppercase">
                {analysis.depth} Mode
              </span>
              <span className="px-2.5 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 text-xs font-semibold uppercase">
                {analysis.language === 'hi' ? 'Hindi' : 'English'}
              </span>
            </div>
            <h1 className="text-xl font-bold text-slate-900 dark:text-white mt-1.5">{document.title}</h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {document.page_count} Pages • Processed with FormEase AI
            </p>
          </div>

          <div className="flex items-center space-x-2.5">
            <button
              onClick={handleCopyMarkdown}
              className="flex items-center space-x-1.5 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 text-xs font-medium transition-colors"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? 'Copied' : 'Copy'}</span>
            </button>
            <button
              onClick={handleDownloadPdf}
              className="flex items-center space-x-1.5 px-3.5 py-2 rounded-xl bg-slate-900 dark:bg-white text-white dark:text-slate-900 hover:bg-slate-800 text-xs font-medium shadow-sm transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download PDF</span>
            </button>
          </div>
        </div>

        {/* 1. Overview Section */}
        {activeSection === 'overview' && (
          <div className="space-y-4">
          {analysisIncomplete && (
            <div role="alert" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
              <p className="font-semibold">Analysis is incomplete</p>
              <p className="mt-1">{analysisFailure || 'One or more analysis batches did not finish.'} Check Reliability &amp; Coverage and retry after the AI provider is available.</p>
              <button onClick={() => setActiveSection('reliability')} className="mt-2 font-semibold underline">View analysis status</button>
            </div>
          )}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
            <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center space-x-2">
              <FileText className="w-5 h-5 text-brand-600" />
              <span>Document Overview</span>
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Subject</span>
                <p className="text-sm font-medium text-slate-800 dark:text-slate-200 mt-1">
                  {analysis.overview?.document_subject || (analysisIncomplete ? 'Unavailable because analysis did not complete.' : 'Not identified in the document.')}
                </p>
              </div>
              <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Main Purpose</span>
                <p className="text-sm font-medium text-slate-800 dark:text-slate-200 mt-1">
                  {analysis.overview?.main_purpose || (analysisIncomplete ? 'Unavailable because analysis did not complete.' : 'Not identified in the document.')}
                </p>
              </div>
              <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Target Audience</span>
                <p className="text-sm font-medium text-slate-800 dark:text-slate-200 mt-1">
                  {analysis.overview?.target_audience || (analysisIncomplete ? 'Unavailable because analysis did not complete.' : 'Not identified in the document.')}
                </p>
              </div>
            </div>
          </div>
          </div>
        )}

        {/* 2. Executive Summary */}
        {activeSection === 'summary' && (
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center space-x-2">
                <Sparkles className="w-5 h-5 text-brand-600" />
                <span>Executive Summary</span>
              </h2>
              <button
                onClick={() => setRefiningComponent('summary')}
                className="flex items-center space-x-1.5 px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-800 text-xs text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800"
              >
                <RotateCcw className="w-3 h-3" />
                <span>Refine</span>
              </button>
            </div>
            <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-line">
              {analysis.summary || 'No summary is available yet. Check the reliability section and retry incomplete analysis.'}
            </p>
          </div>
        )}

        {/* 3. Section-by-Section Explorer */}
        {activeSection === 'sections' && (
          <div className="space-y-4">
            <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center space-x-2">
              <Layers className="w-5 h-5 text-brand-600" />
              <span>Section Explorer</span>
            </h2>
            <div className="space-y-3">
              {savedSections.length ? savedSections.map((sec, idx) => (
                <div
                  key={idx}
                  className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <h3 className="font-semibold text-sm text-slate-900 dark:text-white">
                      {sec.heading}
                    </h3>
                    <div className="flex items-center space-x-2">
                      <span className="text-[11px] px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-500">
                        Page {sec.page_number}
                      </span>
                      {sec.risk_level && (
                        <span
                          className={`text-[11px] px-2 py-0.5 rounded-md font-medium uppercase ${
                            sec.risk_level === 'high'
                              ? 'bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-400'
                              : sec.risk_level === 'medium'
                              ? 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400'
                              : 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400'
                          }`}
                        >
                          {sec.risk_level} risk
                        </span>
                      )}
                    </div>
                  </div>
                  <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                    {sec.simplified_explanation}
                  </p>
                  {sec.key_points && sec.key_points.length > 0 && (
                    <div className="pt-2 border-t border-slate-100 dark:border-slate-800">
                      <span className="text-[11px] font-semibold text-slate-400">Key Points:</span>
                      <ul className="list-disc list-inside text-xs text-slate-600 dark:text-slate-400 mt-1 space-y-1">
                        {sec.key_points.map((kp, kIdx) => (
                          <li key={kIdx}>{kp}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )) : <p className="rounded-lg bg-slate-50 p-4 text-sm text-slate-500 dark:bg-slate-800">No section explanations are available yet. If analysis was incomplete, retry the missing parts from Reliability & Coverage.</p>}
            </div>
          </div>
        )}

        {/* 4. Process & Workflow */}
        {activeSection === 'process' && (
          <div className="min-w-0 max-w-full space-y-4 overflow-x-hidden rounded-2xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <div className="flex min-w-0 max-w-full flex-wrap items-center justify-between gap-3">
              <div className="min-w-0 max-w-full">
                <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center space-x-2">
                  <GitBranch className="w-5 h-5 text-brand-600" />
                  <span className="min-w-0 break-words">{analysis.process_flow.process_title ? `Process: ${analysis.process_flow.process_title}` : 'Process Flow'}</span>
                </h2>
                {(analysis.process_flow.start_state || analysis.process_flow.end_state) && <span className="mt-1 block text-xs text-slate-500">{analysis.process_flow.start_state ? `Start: ${analysis.process_flow.start_state}` : ''}{analysis.process_flow.start_state && analysis.process_flow.end_state ? ' · ' : ''}{analysis.process_flow.end_state ? `End: ${analysis.process_flow.end_state}` : ''}</span>}
              </div>
              {analysis.process_flow.has_process && (
                <div className="flex items-center space-x-1 p-1 bg-slate-100 dark:bg-slate-800 rounded-xl text-xs">
                  <button
                    onClick={() => setProcessView('timeline')}
                    className={`px-3 py-1 rounded-lg font-medium transition-colors ${
                      processView === 'timeline'
                        ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-sm'
                        : 'text-slate-500'
                    }`}
                  >
                    Timeline
                  </button>
                  <button
                    onClick={() => setProcessView('flowchart')}
                    className={`px-3 py-1 rounded-lg font-medium transition-colors ${
                      processView === 'flowchart'
                        ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-sm'
                        : 'text-slate-500'
                    }`}
                  >
                    Flowchart
                  </button>
                </div>
              )}
            </div>

            {!analysis.process_flow.has_process ? (
              <p className="text-sm text-slate-500 dark:text-slate-400 py-4">
                {moduleNeedsRetry('process_flow') ? 'Process analysis did not finish. Retry the missing module in Reliability & Coverage.' : 'No sequential process or workflow was detected in this document.'}
              </p>
            ) : (
              <div className="min-w-0 max-w-full space-y-4">
                {processView === 'timeline' ? (
                  <div className="min-w-0 max-w-full space-y-3 pt-2">
                    {processSteps.map((step, index) => (
                      <button key={index} type="button" onClick={() => setSelectedStepIndex(index)} aria-pressed={selectedStepIndex === index}
                        className={`flex w-full min-w-0 max-w-full items-start gap-3.5 rounded-xl p-3 text-left ${selectedStepIndex === index ? 'bg-brand-50 dark:bg-brand-900/20' : 'hover:bg-slate-50 dark:hover:bg-slate-800'}`}>
                        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-500/10 text-xs font-bold text-brand-600 dark:text-brand-400">{step.step_number || index + 1}</span>
                        <span className="min-w-0 max-w-full break-words">
                          <span className="block text-sm font-semibold text-slate-800 dark:text-slate-200">{step.title}</span>
                          <span className="mt-0.5 block text-xs text-slate-600 dark:text-slate-400">{step.summary || step.description}</span>
                          {step.condition && <span className="mt-1 block text-[11px] text-amber-600 dark:text-amber-400">Condition: {step.condition}</span>}
                        </span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="min-w-0 max-w-full space-y-4">
                    {processDiagram ? (
                      <MermaidDiagram
                        title={analysis.process_flow.process_title || 'Document process flow'}
                        chart={processDiagram}
                        onNodeClick={handleProcessDiagramNodeClick}
                        selectedNodeId={`S${selectedStepIndex + 1}`}
                      />
                    ) : <p className="text-sm text-slate-500">No flowchart syntax is available; select a step below to view its details.</p>}
                    <div className="grid min-w-0 max-w-full gap-2 sm:grid-cols-2">
                      {processSteps.map((step, index) => (
                        <button key={index} type="button" onClick={() => setSelectedStepIndex(index)}
                          aria-pressed={selectedStepIndex === index}
                          className={`min-w-0 max-w-full break-words rounded-lg border p-3 text-left ${selectedStepIndex === index ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/20' : 'border-slate-200 hover:border-brand-500 dark:border-slate-700'}`}>
                          <span className="block break-words text-sm font-semibold">{index + 1}. {step.title}</span>
                          <span className="mt-1 block break-words text-xs text-slate-500">{step.summary || step.description}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {selectedProcessStep && (
                  <ProcessStepDetails
                    step={selectedProcessStep}
                    index={selectedStepIndex}
                    total={processSteps.length}
                    previousStep={processSteps[selectedStepIndex - 1]}
                    nextStep={processSteps[selectedStepIndex + 1]}
                    onSelectStep={setSelectedStepIndex}
                  />
                )}
              </div>
            )}
          </div>
        )}

        {/* 5. Key Information */}
        {activeSection === 'concept_map' && (
          <div className="min-w-0 max-w-full space-y-4 overflow-x-hidden rounded-2xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <h2 className="text-lg font-bold text-slate-900 dark:text-white">Document Concept Map</h2>
            {analysis.concept_map?.central_topic && <p className="text-sm text-slate-600 dark:text-slate-300">Central topic: <strong>{analysis.concept_map.central_topic}</strong></p>}
            {analysis.concept_map?.concepts?.length ? (
              <>
                {conceptMapNeedsRefresh && (
                  <div className="flex min-w-0 max-w-full flex-col gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200 sm:flex-row sm:items-center sm:justify-between">
                    <p className="min-w-0 max-w-full break-words whitespace-normal">
                      This saved Concept Map is missing structured node details. Re-analyze this module to update the explanations and technical details.
                    </p>
                    <button
                      type="button"
                      onClick={handleReanalyzeConceptMap}
                      disabled={isReanalyzingConceptMap}
                      className="shrink-0 rounded-lg bg-amber-700 px-3 py-2 text-xs font-semibold text-white hover:bg-amber-800 disabled:cursor-wait disabled:opacity-60 dark:bg-amber-600 dark:hover:bg-amber-500"
                    >
                      {isReanalyzingConceptMap ? 'Re-analyzing…' : 'Re-analyze Concept Map'}
                    </button>
                  </div>
                )}
                {analysis.concept_map.mermaid_syntax && <MermaidDiagram title={`${analysis.concept_map.central_topic || 'Document'} concept map`} chart={analysis.concept_map.mermaid_syntax} zoomable />}
                <div className="grid min-w-0 max-w-full gap-3 sm:grid-cols-2">
                  {analysis.concept_map.concepts.map((concept, index) => (
                    <button key={`${concept.name}-${index}`} onClick={() => setSelectedConcept(index)} aria-pressed={selectedConcept === index}
                      className={`min-w-0 max-w-full rounded-xl border p-4 text-left ${selectedConcept === index ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/20' : 'border-slate-200 dark:border-slate-800'}`}>
                      <span className="block max-w-full break-words whitespace-normal text-sm font-semibold">{concept.name}</span>
                      <span className="mt-1 block text-xs text-slate-500">Page {concept.page_number || 'reference not identified'}</span>
                    </button>
                  ))}
                </div>
                {selectedConcept !== null && analysis.concept_map.concepts[selectedConcept] && (
                  <article
                    className="min-w-0 max-w-full break-words whitespace-normal rounded-xl border border-brand-200 p-4 dark:border-brand-800 [&_h3]:max-w-full [&_h3]:break-words [&_h3]:whitespace-normal [&_h4]:max-w-full [&_h4]:break-words [&_h4]:whitespace-normal [&_li]:max-w-full [&_li]:break-words [&_li]:whitespace-normal [&_p]:max-w-full [&_p]:break-words [&_p]:whitespace-normal"
                    aria-live="polite"
                  >
                    <h3 className="text-lg font-semibold">{analysis.concept_map.concepts[selectedConcept].name}</h3>
                    {analysis.concept_map.concepts[selectedConcept].page_number && (
                      <p className="mt-1 text-xs text-slate-500">Source page: {analysis.concept_map.concepts[selectedConcept].page_number}</p>
                    )}
                    <div className="mt-4 space-y-4">
                      <section>
                        <h4 className="font-semibold text-sm">Detailed Explanation</h4>
                        {(analysis.concept_map.concepts[selectedConcept].detailed_explanation || analysis.concept_map.concepts[selectedConcept].description)
                          .split(/\n\s*\n/)
                          .filter(Boolean)
                          .map((paragraph, index) => <p key={index} className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{paragraph}</p>)}
                      </section>
                      <section>
                        <h4 className="font-semibold text-sm">Key Responsibilities</h4>
                        {analysis.concept_map.concepts[selectedConcept].key_responsibilities?.length ? (
                          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600 dark:text-slate-300">
                            {analysis.concept_map.concepts[selectedConcept].key_responsibilities.map((item, index) => <li key={index}>{item}</li>)}
                          </ul>
                        ) : <p className="mt-2 text-sm text-slate-500">No responsibilities were available in this saved analysis.</p>}
                      </section>
                      <section>
                        <h4 className="font-semibold text-sm">Protocols, Hardware &amp; Standards</h4>
                        {analysis.concept_map.concepts[selectedConcept].protocols_hardware_standards?.length ? (
                          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600 dark:text-slate-300">
                            {analysis.concept_map.concepts[selectedConcept].protocols_hardware_standards.map((item, index) => <li key={index}>{item}</li>)}
                          </ul>
                        ) : <p className="mt-2 text-sm text-slate-500">No examples were identified for this concept.</p>}
                      </section>
                      <section>
                        <h4 className="font-semibold text-sm">Data Unit (PDU) &amp; Interaction</h4>
                        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                          <strong>PDU:</strong> {analysis.concept_map.concepts[selectedConcept].data_unit || 'Not applicable or not identified.'}
                        </p>
                        <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-300">
                          {analysis.concept_map.concepts[selectedConcept].data_unit_interaction || 'Layer interactions were not identified in this saved analysis.'}
                        </p>
                      </section>
                      <section className="space-y-1 border-t border-slate-200 pt-3 text-xs text-slate-500 dark:border-slate-700">
                        <h4 className="font-semibold">Connections in this map</h4>
                        {analysis.concept_map.relationships.filter((item) => item.from === analysis.concept_map?.concepts[selectedConcept].name || item.to === analysis.concept_map?.concepts[selectedConcept].name).map((item, index) => (
                          <p key={`${item.from}-${item.to}-${index}`}>{item.from} {item.label || 'relates to'} {item.to}{item.page_number ? ` · Page ${item.page_number}` : ''}</p>
                        ))}
                      </section>
                    </div>
                  </article>
                )}
              </>
            ) : <p className="text-sm text-slate-500">{moduleNeedsRetry('concept_map') ? 'Concept map analysis did not finish. Retry the missing module in Reliability & Coverage.' : 'No document-supported concept relationships were identified in the completed analysis.'}</p>}
          </div>
        )}

        {activeSection === 'revision' && (
          <div className="space-y-4">
            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <h2 className="text-lg font-bold">Revision Notes</h2>
              {analysis.revision_notes?.length ? <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-slate-700 dark:text-slate-300">{analysis.revision_notes.map((note, index) => <li key={index}>{note}</li>)}</ul> : <p className="mt-3 text-sm text-slate-500">{moduleNeedsRetry('revision_notes') ? 'Revision notes did not finish. Retry the missing module in Reliability & Coverage.' : 'No document-supported revision notes were produced.'}</p>}
            </section>
            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <h2 className="text-lg font-bold">Formulas</h2>
              {analysis.formulas?.length ? analysis.formulas.map((item, index) => <article key={`${item.formula}-${index}`} className="mt-3 rounded-xl bg-slate-50 p-4 dark:bg-slate-800"><p className="font-mono text-sm font-semibold">{item.formula}</p><p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{item.explanation}</p>{item.page_number && <p className="mt-2 text-xs text-slate-400">Page {item.page_number}</p>}</article>) : <p className="mt-3 text-sm text-slate-500">{moduleNeedsRetry('formulas') ? 'Formula extraction did not finish. Retry the missing module in Reliability & Coverage.' : 'No formulas were identified in the source text.'}</p>}
            </section>
          </div>
        )}

        {/* 6. Key Information */}
        {activeSection === 'key_info' && (
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-5">
            <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center space-x-2">
              <AlertTriangle className="w-5 h-5 text-amber-500" />
              <span>Key Information & Obligations</span>
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 rounded-xl border border-rose-100 dark:border-rose-900/30 bg-rose-50/30 dark:bg-rose-950/20">
                <h3 className="text-xs font-bold text-rose-700 dark:text-rose-400 uppercase tracking-wider mb-2">
                  Critical Obligations
                </h3>
                <ul className="list-disc list-inside text-xs text-slate-700 dark:text-slate-300 space-y-1">
                  {analysis.key_information.critical_obligations?.length ? analysis.key_information.critical_obligations.map((item, i) => (
                    <li key={i}>{item}</li>
                  )) : <li>{moduleNeedsRetry('key_information') ? 'Key information extraction did not finish. Retry the missing module in Reliability & Coverage.' : 'No supported obligations were extracted.'}</li>}
                </ul>
              </div>

              <div className="p-4 rounded-xl border border-blue-100 dark:border-blue-900/30 bg-blue-50/30 dark:bg-blue-950/20">
                <h3 className="text-xs font-bold text-blue-700 dark:text-blue-400 uppercase tracking-wider mb-2">
                  Deadlines & Dates
                </h3>
                <ul className="list-disc list-inside text-xs text-slate-700 dark:text-slate-300 space-y-1">
                  {analysis.key_information.deadlines_and_dates?.length ? analysis.key_information.deadlines_and_dates.map((item, i) => (
                    <li key={i}>{item}</li>
                  )) : <li>{moduleNeedsRetry('key_information') ? 'Key information extraction did not finish; retry the missing module.' : 'No document-grounded dates were extracted.'}</li>}
                </ul>
              </div>
              <div className="p-4 rounded-xl border border-amber-100 dark:border-amber-900/30 bg-amber-50/30 dark:bg-amber-950/20">
                <h3 className="text-xs font-bold text-amber-700 dark:text-amber-400 uppercase tracking-wider mb-2">Warnings & Penalties</h3>
                <ul className="list-disc list-inside text-xs text-slate-700 dark:text-slate-300 space-y-1">
                  {analysis.key_information.warnings_and_penalties?.length ? analysis.key_information.warnings_and_penalties.map((item, i) => <li key={i}>{item}</li>) : <li>{moduleNeedsRetry('key_information') ? 'Key information extraction did not finish; retry the missing module.' : 'No supported warnings or penalties were extracted.'}</li>}
                </ul>
              </div>
              <div className="p-4 rounded-xl border border-violet-100 dark:border-violet-900/30 bg-violet-50/30 dark:bg-violet-950/20">
                <h3 className="text-xs font-bold text-violet-700 dark:text-violet-400 uppercase tracking-wider mb-2">Important Conditions</h3>
                <ul className="list-disc list-inside text-xs text-slate-700 dark:text-slate-300 space-y-1">
                  {analysis.key_information.important_conditions?.length ? analysis.key_information.important_conditions.map((item, i) => <li key={i}>{item}</li>) : <li>{moduleNeedsRetry('key_information') ? 'Key information extraction did not finish; retry the missing module.' : 'No supported conditions were extracted.'}</li>}
                </ul>
              </div>
              {analysis.key_information.important_facts?.length ? (
                <div className="p-4 rounded-xl border border-emerald-100 dark:border-emerald-900/30 bg-emerald-50/30 dark:bg-emerald-950/20">
                  <h3 className="text-xs font-bold text-emerald-700 dark:text-emerald-400 uppercase tracking-wider mb-2">Important Facts & Figures</h3>
                  <ul className="list-disc list-inside text-xs text-slate-700 dark:text-slate-300 space-y-1">
                    {analysis.key_information.important_facts.map((item, i) => <li key={i}>{item}</li>)}
                  </ul>
                </div>
              ) : null}
            </div>
          </div>
        )}

        {/* 6. Definitions */}
        {activeSection === 'definitions' && (
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
            <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center space-x-2">
              <BookOpen className="w-5 h-5 text-brand-600" />
              <span>Definitions & Glossary</span>
            </h2>
            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              {analysis.definitions?.length ? analysis.definitions.map((d, i) => (
                <div key={i} className="py-3">
                  <h4 className="font-semibold text-sm text-slate-900 dark:text-white">{d.term}</h4>
                  <p className="text-xs text-slate-600 dark:text-slate-300 mt-1">{d.plain_definition}</p>
                </div>
              )) : <p className="text-xs text-slate-500">{moduleNeedsRetry('definitions') ? 'Definitions extraction did not finish. Retry the missing module in Reliability & Coverage.' : 'No document-grounded definitions were extracted.'}</p>}
            </div>
          </div>
        )}

        {/* 7. Recommendations */}
        {activeSection === 'recommendations' && (
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
            <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center space-x-2">
              <Lightbulb className="w-5 h-5 text-amber-500" />
              <span>Contextual Recommendations</span>
            </h2>
            <div className="space-y-3">
              {analysis.recommendations?.length ? analysis.recommendations.map((r, i) => (
                <div key={i} className="p-4 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/40">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-400">
                      {r.category || 'Action Item'}
                    </span>
                    {r.source_reference && (
                      <span className="text-[11px] text-slate-400">Ref: {r.source_reference}</span>
                    )}
                  </div>
                  <p className="text-xs text-slate-700 dark:text-slate-300 mt-2 font-medium">
                    {r.recommendation}
                  </p>
                </div>
              )) : <p className="text-xs text-slate-500">{moduleNeedsRetry('recommendations') ? 'Recommendations did not finish. Retry the missing module in Reliability & Coverage.' : 'No document-grounded recommendations were extracted.'}</p>}
            </div>
          </div>
        )}

        {/* 8. Reliability & Coverage */}
        {activeSection === 'reliability' && (
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
            <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center space-x-2">
              <ShieldCheck className="w-5 h-5 text-emerald-600" />
              <span>Reliability & Source Evidence Report</span>
            </h2>
            <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/40 space-y-3 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Document Page Coverage:</span>
                <span className="font-semibold text-slate-800 dark:text-slate-200">
                  {analysis.reliability_report?.coverage_pages || document.page_count} Pages
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Analysis completion:</span>
                <span className={`font-semibold ${analysis.reliability_report?.is_complete === false ? 'text-amber-600' : 'text-emerald-600'}`}>
                  {analysis.reliability_report?.is_complete === false ? 'Partial · retry available' : 'All requested batches completed'}
                </span>
              </div>
              {typeof analysis.reliability_report?.total_batches === 'number' && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Analysis batches:</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200">{analysis.reliability_report.completed_batches?.length || 0} / {analysis.reliability_report.total_batches} completed</span>
                </div>
              )}
              {analysis.reliability_report?.is_complete === false && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300">
                  <p className="font-semibold">Some analysis parts did not finish.</p>
                  <p className="mt-1">Completed parts are saved. Retry will request only the missing parts.</p>
                  <button onClick={onRetryAnalysis} className="mt-2 rounded-lg bg-amber-700 px-3 py-1.5 text-white hover:bg-amber-800">Retry missing parts</button>
                </div>
              )}
              {analysis.reliability_report?.warnings && analysis.reliability_report.warnings.length > 0 ? (
                <div className="pt-2 border-t border-slate-200 dark:border-slate-800 text-amber-600">
                  <span className="font-semibold">Processing warnings:</span>
                  <ul className="list-disc list-inside mt-1 space-y-1">
                    {analysis.reliability_report.warnings.map((w, idx) => (
                      <li key={idx}>{w}</li>
                    ))}
                  </ul>
                </div>
              ) : analysis.reliability_report?.is_complete !== false ? (
                <p className="text-emerald-600 pt-2 border-t border-slate-200 dark:border-slate-800">
                  No extraction warnings detected. Document text is intact.
                </p>
              ) : null}
            </div>
          </div>
        )}
      </div>

      {/* Refine Component Modal */}
      {refiningComponent && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <h3 className="text-base font-bold text-slate-900 dark:text-white">
              Refine {refiningComponent}
            </h3>
            <p className="text-xs text-slate-500">
              Provide custom instructions (e.g. &ldquo;Make this simpler&rdquo;, &ldquo;Convert to bullet points&rdquo;, &ldquo;Shorten to 2 sentences&rdquo;).
            </p>
            <textarea
              rows={3}
              value={refineInstruction}
              onChange={(e) => setRefineInstruction(e.target.value)}
              placeholder="Enter refinement instructions..."
              className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800 text-xs focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
            <div className="flex justify-end space-x-2">
              <button
                onClick={() => setRefiningComponent(null)}
                className="px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-medium text-slate-600"
              >
                Cancel
              </button>
              <button
                onClick={handleRefine}
                disabled={isRefining || !refineInstruction.trim()}
                className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-xs font-medium"
              >
                {isRefining ? 'Revising...' : 'Apply Revision'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
