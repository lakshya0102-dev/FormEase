'use client';

import React from 'react';
import { 
  LayoutDashboard, 
  FilePlus2, 
  FolderArchive, 
  Trash2, 
  Settings, 
  UserCircle2, 
  ChevronLeft, 
  ChevronRight,
  Sparkles
} from 'lucide-react';

export type NavItem = 'dashboard' | 'upload' | 'library' | 'trash' | 'settings' | 'profile';

interface SidebarProps {
  activeTab: NavItem;
  setActiveTab: (tab: NavItem) => void;
  collapsed: boolean;
  setCollapsed: (collapsed: boolean) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  setActiveTab,
  collapsed,
  setCollapsed,
}) => {
  const menuItems = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'upload', label: 'New Analysis', icon: FilePlus2 },
    { id: 'library', label: 'Document Library', icon: FolderArchive },
    { id: 'trash', label: 'Recently Deleted', icon: Trash2 },
    { id: 'settings', label: 'Settings', icon: Settings },
    { id: 'profile', label: 'Profile', icon: UserCircle2 },
  ];

  return (
    <aside
      className={`relative flex flex-col border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 transition-all duration-300 ${
        collapsed ? 'w-20' : 'w-64'
      }`}
    >
      {/* Brand Logo & Title */}
      <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-800 h-16">
        <div className="flex items-center space-x-3 overflow-hidden">
          <div className="p-2 rounded-xl bg-brand-500/10 dark:bg-brand-500/20 text-brand-600 dark:text-brand-400">
            <Sparkles className="w-5 h-5" />
          </div>
          {!collapsed && (
            <div className="leading-tight">
              <h1 className="font-bold text-slate-900 dark:text-white text-lg tracking-tight">FormEase</h1>
              <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase tracking-widest font-semibold">
                AI Simplifier
              </p>
            </div>
          )}
        </div>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>

      {/* Navigation Items */}
      <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
        {menuItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id as NavItem)}
              className={`w-full flex items-center px-3 py-2.5 rounded-xl font-medium text-sm transition-colors ${
                isActive
                  ? 'bg-brand-50 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300 shadow-sm'
                  : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/60 hover:text-slate-900 dark:hover:text-slate-100'
              } ${collapsed ? 'justify-center' : 'space-x-3'}`}
            >
              <Icon className={`w-5 h-5 flex-shrink-0 ${isActive ? 'text-brand-600 dark:text-brand-400' : ''}`} />
              {!collapsed && <span>{item.label}</span>}
            </button>
          );
        })}
      </nav>

      {/* Tagline Footer */}
      {!collapsed && (
        <div className="p-4 border-t border-slate-200 dark:border-slate-800 text-[11px] text-slate-400 dark:text-slate-500 leading-relaxed">
          Understand Documents.<br />
          Simplify Complexity.<br />
          Step by Step.
        </div>
      )}
    </aside>
  );
};
