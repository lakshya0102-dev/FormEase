'use client';

import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';
import { useTheme } from '@/components/providers/ThemeProvider';

const MIN_ZOOM = 0.25;
const MAX_ZOOM = 4;

export function MermaidDiagram({
  chart,
  title = 'Document diagram',
  zoomable = false,
  onNodeClick,
  selectedNodeId,
}: {
  chart: string;
  title?: string;
  zoomable?: boolean;
  onNodeClick?: (nodeId: string) => void;
  selectedNodeId?: string;
}) {
  const reactId = useId();
  const { theme } = useTheme();
  const [svg, setSvg] = useState('');
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [svgSize, setSvgSize] = useState({ width: 0, height: 0 });
  const viewportRef = useRef<HTMLDivElement>(null);
  const svgHostRef = useRef<HTMLDivElement>(null);
  const zoomRef = useRef(1);
  const pendingAnchorRef = useRef<{ x: number; y: number; contentX: number; contentY: number } | null>(null);
  const gestureStartZoom = useRef(1);
  const renderId = `formease-${reactId.replace(/[^a-zA-Z0-9_-]/g, '')}`;

  useEffect(() => {
    let cancelled = false;
    setError('');
    setSvg('');
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'strict',
      theme: theme === 'dark' ? 'dark' : 'default',
    });
    mermaid.render(renderId, chart)
      .then(({ svg: renderedSvg }) => {
        if (!cancelled) setSvg(renderedSvg);
      })
      .catch(() => {
        if (!cancelled) setError('This diagram could not be rendered. The related explanation remains available.');
      });

    return () => { cancelled = true; };
  }, [chart, renderId, theme]);

  useEffect(() => {
    zoomRef.current = 1;
    setZoom(1);
    setSvgSize({ width: 0, height: 0 });
  }, [chart]);

  useEffect(() => {
    if (!zoomable || !svg) return;
    const element = svgHostRef.current?.querySelector('svg');
    if (!element) return;
    const viewBox = element.viewBox.baseVal;
    const bounds = element.getBBox();
    const width = viewBox.width || bounds.width;
    const height = viewBox.height || bounds.height;
    if (!width || !height) return;
    element.style.setProperty('max-width', 'none', 'important');
    element.style.width = `${width}px`;
    element.style.height = `${height}px`;
    element.style.display = 'block';
    setSvgSize({ width, height });
  }, [svg, zoomable]);

  useEffect(() => {
    if (!onNodeClick || !svg) return;
    const root = viewportRef.current;
    if (!root) return;
    const cleanups: Array<() => void> = [];

    root.querySelectorAll<SVGGElement>('g.node[id]').forEach((node) => {
      const nodeId = node.getAttribute('data-id') || node.id.match(/^flowchart-(.+)-\d+$/)?.[1] || '';
      if (!nodeId) return;
      const selectNode = () => onNodeClick(nodeId);
      const onKeyDown = (event: KeyboardEvent) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          selectNode();
        }
      };
      node.style.cursor = 'pointer';
      node.setAttribute('tabindex', '0');
      node.setAttribute('role', 'button');
      node.setAttribute('aria-label', `Select ${nodeId}`);
      node.addEventListener('click', selectNode);
      node.addEventListener('keydown', onKeyDown);
      cleanups.push(() => {
        node.style.cursor = '';
        node.removeAttribute('tabindex');
        node.removeAttribute('role');
        node.removeAttribute('aria-label');
        node.removeAttribute('aria-pressed');
        node.style.filter = '';
        node.removeEventListener('click', selectNode);
        node.removeEventListener('keydown', onKeyDown);
      });
    });

    return () => cleanups.forEach((cleanup) => cleanup());
  }, [svg, onNodeClick]);

  useEffect(() => {
    if (!svg) return;
    viewportRef.current?.querySelectorAll<SVGGElement>('g.node[id]').forEach((node) => {
      const nodeId = node.getAttribute('data-id') || node.id.match(/^flowchart-(.+)-\d+$/)?.[1] || '';
      const selected = Boolean(selectedNodeId && nodeId === selectedNodeId);
      node.style.filter = selected ? 'drop-shadow(0 0 5px rgba(14, 165, 233, 0.9))' : '';
      if (onNodeClick) node.setAttribute('aria-pressed', String(selected));
    });
  }, [svg, selectedNodeId, onNodeClick]);

  const zoomAt = useCallback((requestedZoom: number, x?: number, y?: number) => {
    const viewport = viewportRef.current;
    const previousZoom = zoomRef.current;
    const nextZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, requestedZoom));
    if (nextZoom === previousZoom) return;
    const anchorX = x ?? (viewport ? viewport.clientWidth / 2 : 0);
    const anchorY = y ?? (viewport ? viewport.clientHeight / 2 : 0);
    pendingAnchorRef.current = viewport ? {
      x: anchorX,
      y: anchorY,
      contentX: (viewport.scrollLeft + anchorX) / previousZoom,
      contentY: (viewport.scrollTop + anchorY) / previousZoom,
    } : null;
    zoomRef.current = nextZoom;
    setZoom(nextZoom);
  }, []);

  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    const anchor = pendingAnchorRef.current;
    if (!viewport || !anchor) return;
    viewport.scrollLeft = anchor.contentX * zoom - anchor.x;
    viewport.scrollTop = anchor.contentY * zoom - anchor.y;
    pendingAnchorRef.current = null;
  }, [zoom]);

  useEffect(() => {
    if (!zoomable) return;
    const viewport = viewportRef.current;
    if (!viewport) return;
    const wheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      const rect = viewport.getBoundingClientRect();
      const delta = event.deltaMode === WheelEvent.DOM_DELTA_LINE
        ? event.deltaY * 16
        : event.deltaMode === WheelEvent.DOM_DELTA_PAGE
          ? event.deltaY * viewport.clientHeight
          : event.deltaY;
      zoomAt(zoomRef.current * Math.exp(-delta * 0.002), event.clientX - rect.left, event.clientY - rect.top);
    };
    const gestureChange = (event: Event) => {
      const gesture = event as Event & { scale?: number; clientX?: number; clientY?: number };
      if (typeof gesture.scale !== 'number') return;
      event.preventDefault();
      const rect = viewport.getBoundingClientRect();
      zoomAt(
        gestureStartZoom.current * gesture.scale,
        typeof gesture.clientX === 'number' ? gesture.clientX - rect.left : undefined,
        typeof gesture.clientY === 'number' ? gesture.clientY - rect.top : undefined,
      );
    };
    const gestureStart = () => { gestureStartZoom.current = zoomRef.current; };
    viewport.addEventListener('wheel', wheel, { passive: false });
    viewport.addEventListener('gesturestart', gestureStart);
    viewport.addEventListener('gesturechange', gestureChange, { passive: false });
    return () => {
      viewport.removeEventListener('wheel', wheel);
      viewport.removeEventListener('gesturestart', gestureStart);
      viewport.removeEventListener('gesturechange', gestureChange);
    };
  }, [zoomable, zoomAt, expanded, svg]);

  const changeZoom = (amount: number) => zoomAt(zoomRef.current + amount);
  const resetZoom = () => zoomAt(1);

  return (
    <section className={expanded
      ? 'fixed inset-3 z-[100] flex min-w-0 max-w-full flex-col overflow-hidden rounded-2xl border border-slate-300 bg-white p-4 shadow-2xl dark:border-slate-700 dark:bg-slate-950 sm:inset-6'
      : 'relative w-full min-w-0 max-w-full overflow-hidden rounded-xl bg-slate-50/70 p-3 dark:bg-slate-800/40'} aria-label={title}>
      <header className="mb-2 flex items-center justify-between gap-3">
        <h3 className="min-w-0 break-words text-sm font-semibold text-slate-800 dark:text-slate-200">{title}</h3>
        <div className="flex shrink-0 items-center gap-2">
          {zoomable && (
            <div className="flex items-center gap-1" aria-label="Diagram zoom controls">
              <button type="button" onClick={() => changeZoom(-0.25)} disabled={zoom <= MIN_ZOOM}
                aria-label="Zoom out" className="rounded-lg border border-slate-300 px-2 py-1 text-sm font-medium hover:border-brand-500 disabled:opacity-40 dark:border-slate-600">−</button>
              <button type="button" onClick={resetZoom} aria-label="Reset zoom"
                className="min-w-12 rounded-lg border border-slate-300 px-2 py-1 text-xs font-medium hover:border-brand-500 dark:border-slate-600">{Math.round(zoom * 100)}%</button>
              <button type="button" onClick={() => changeZoom(0.25)} disabled={zoom >= MAX_ZOOM}
                aria-label="Zoom in" className="rounded-lg border border-slate-300 px-2 py-1 text-sm font-medium hover:border-brand-500 disabled:opacity-40 dark:border-slate-600">+</button>
            </div>
          )}
          <button type="button" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}
            className="rounded-lg border border-slate-300 px-3 py-1 text-xs font-medium hover:border-brand-500 dark:border-slate-600">
            {expanded ? 'Close large view' : 'Open large view'}
          </button>
        </div>
      </header>
      {error ? <p className="text-xs text-amber-700 dark:text-amber-300" role="status">{error}</p>
        : !svg ? <p className="text-xs text-slate-400" role="status">Rendering diagram…</p>
          : zoomable
          ? <div ref={viewportRef} className={expanded ? 'min-h-0 min-w-0 max-w-full flex-1 overflow-auto' : 'max-h-[32rem] min-w-0 max-w-full overflow-auto'}>
              <div className="relative" style={{ width: svgSize.width * zoom, height: svgSize.height * zoom }}>
                <div
                  ref={svgHostRef}
                  className="absolute left-0 top-0 [&>svg]:max-w-none"
                  style={{
                    width: svgSize.width,
                    height: svgSize.height,
                    transform: `scale(${zoom})`,
                    transformOrigin: 'top left',
                  }}
                  dangerouslySetInnerHTML={{ __html: svg }}
                />
              </div>
            </div>
            : <div ref={viewportRef} className={expanded ? 'min-h-0 min-w-0 max-w-full flex-1 overflow-x-auto overflow-y-auto [&>svg]:mx-auto [&>svg]:h-auto [&>svg]:max-w-none' : 'max-h-[32rem] min-w-0 max-w-full overflow-x-auto overflow-y-auto [&>svg]:mx-auto [&>svg]:h-auto [&>svg]:max-w-full'} dangerouslySetInnerHTML={{ __html: svg }} />}
    </section>
  );
}
