'use client';

import React from 'react';
import { Sun, Moon, CheckCircle2, AlertTriangle, XCircle, LogOut } from 'lucide-react';

interface HeaderProps {
  darkMode: boolean;
  setDarkMode: (val: boolean) => void;
  accountEmail: string;
  onSignOut: () => void;
  aiStatus: {
    provider: string;
    connected: boolean;
    modelInstalled: boolean;
    modelName: string;
    detail: string;
  };
}

export const Header: React.FC<HeaderProps> = ({ darkMode, setDarkMode, aiStatus, accountEmail, onSignOut }) => {
  const providerName = aiStatus.provider === 'openrouter' ? 'OpenRouter' : aiStatus.provider;
  return (
    <header className="h-16 border-b border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md px-6 flex items-center justify-between sticky top-0 z-20">
      {/* Search / Breadcrumb Placeholder */}
      <div className="flex items-center space-x-3 text-sm text-slate-500 dark:text-slate-400">
        <span className="font-medium text-slate-800 dark:text-slate-200">FormEase Workspace</span>
      </div>

      {/* Right controls: AI status pill, theme switch, notifications */}
      <div className="flex items-center space-x-4">
        {/* Configured AI provider status */}
        <div
          className={`flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-medium border ${
            aiStatus.connected && (aiStatus.provider === 'openrouter' || aiStatus.modelInstalled)
              ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800'
              : aiStatus.connected
              ? 'bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800'
              : 'bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-400 border-rose-200 dark:border-rose-800'
          }`}
          title={aiStatus.detail}
        >
          {aiStatus.connected && (aiStatus.provider === 'openrouter' || aiStatus.modelInstalled) ? (
            <CheckCircle2 className="w-3.5 h-3.5" />
          ) : aiStatus.connected ? (
            <AlertTriangle className="w-3.5 h-3.5" />
          ) : (
            <XCircle className="w-3.5 h-3.5" />
          )}
          <span>
            {aiStatus.connected && (aiStatus.provider === 'openrouter' || aiStatus.modelInstalled)
              ? `${providerName} configured: ${aiStatus.modelName}`
              : aiStatus.connected
              ? 'Model Missing'
              : 'AI Disconnected'}
          </span>
        </div>

        {/* Theme toggle */}
        <button
          onClick={() => setDarkMode(!darkMode)}
          className="p-2 rounded-xl text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          title={darkMode ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
        >
          {darkMode ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-slate-600" />}
        </button>

        {/* Signed-in user */}
        <div className="flex items-center gap-2 border-l border-slate-200 pl-3 dark:border-slate-800">
          <div className="w-8 h-8 rounded-full bg-brand-500/20 text-brand-700 dark:text-brand-300 font-semibold flex items-center justify-center text-xs">
            {(accountEmail[0] || 'U').toUpperCase()}
          </div>
          <span className="text-sm font-medium text-slate-700 dark:text-slate-300 hidden md:inline">
            {accountEmail}
          </span>
          <button onClick={onSignOut} aria-label="Sign out" title="Sign out" className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white">
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </header>
  );
};
