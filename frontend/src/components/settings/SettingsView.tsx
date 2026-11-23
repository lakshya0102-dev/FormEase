'use client';

import React, { useState } from 'react';
import { SupportedLanguage, ExplanationLevel } from '@/types';

interface SettingsViewProps {
  language: SupportedLanguage;
  setLanguage: (lang: SupportedLanguage) => void;
  depth: ExplanationLevel;
  setDepth: (depth: ExplanationLevel) => void;
  aiStatus: {
    provider: string;
    connected: boolean;
    modelInstalled: boolean;
    modelName: string;
    detail: string;
  };
}

export const SettingsView: React.FC<SettingsViewProps> = ({
  language,
  setLanguage,
  depth,
  setDepth,
  aiStatus,
}) => {
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    localStorage.setItem('formease_lang', language);
    localStorage.setItem('formease_depth', depth);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Settings & Preferences</h2>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Configure default document simplification preferences and view the backend AI configuration.
        </p>
      </div>

      {/* Analysis Defaults */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-5">
        <h3 className="font-semibold text-sm text-slate-900 dark:text-white">Analysis Defaults</h3>

        {/* Language Selection */}
        <div>
          <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-2">
            Output Language
          </label>
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => setLanguage('en')}
              className={`p-3 rounded-xl border text-xs font-medium text-left transition-all ${
                language === 'en'
                  ? 'border-brand-500 bg-brand-50/50 dark:bg-brand-900/20 text-brand-700 dark:text-brand-300'
                  : 'border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-50'
              }`}
            >
              <div className="font-bold">English</div>
              <div className="text-[11px] text-slate-400 mt-0.5">Standard plain English output</div>
            </button>
            <button
              type="button"
              onClick={() => setLanguage('hi')}
              className={`p-3 rounded-xl border text-xs font-medium text-left transition-all ${
                language === 'hi'
                  ? 'border-brand-500 bg-brand-50/50 dark:bg-brand-900/20 text-brand-700 dark:text-brand-300'
                  : 'border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-50'
              }`}
            >
              <div className="font-bold">Hindi (हिंदी)</div>
              <div className="text-[11px] text-slate-400 mt-0.5">Clear Devanagari Hindi simplification</div>
            </button>
          </div>
        </div>

        {/* Depth Selection */}
        <div>
          <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-2">
            Explanation Depth
          </label>
          <div className="grid grid-cols-3 gap-3">
            {[
              { id: 'simple', label: 'Simple', desc: 'Everyday words, easy analogies' },
              { id: 'balanced', label: 'Balanced', desc: 'Clarity with necessary technical terms' },
              { id: 'detailed', label: 'Detailed', desc: 'Comprehensive depth and conditions' },
            ].map((lvl) => (
              <button
                key={lvl.id}
                type="button"
                onClick={() => setDepth(lvl.id as ExplanationLevel)}
                className={`p-3 rounded-xl border text-xs font-medium text-left transition-all ${
                  depth === lvl.id
                    ? 'border-brand-500 bg-brand-50/50 dark:bg-brand-900/20 text-brand-700 dark:text-brand-300'
                    : 'border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-50'
                }`}
              >
                <div className="font-bold">{lvl.label}</div>
                <div className="text-[10px] text-slate-400 mt-0.5">{lvl.desc}</div>
              </button>
            ))}
          </div>
        </div>

        <button
          onClick={handleSave}
          className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-700 text-white text-xs font-medium shadow-sm transition-colors"
        >
          {saved ? 'Preferences Saved!' : 'Save Preferences'}
        </button>
      </div>

      {/* Backend AI provider */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
        <h3 className="font-semibold text-sm text-slate-900 dark:text-white">Configured AI Provider</h3>
        <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
          AI requests are sent by the FormEase backend to its configured provider. Provider credentials remain on the server.
        </p>
        <div className="text-xs text-slate-500 flex items-center space-x-2 pt-2">
          <span className="font-semibold">{aiStatus.provider} · {aiStatus.modelName}:</span>
          <span className={aiStatus.connected && aiStatus.modelInstalled ? 'text-emerald-600' : 'text-amber-600'}>
            {aiStatus.detail}
          </span>
        </div>
      </div>
    </div>
  );
};
