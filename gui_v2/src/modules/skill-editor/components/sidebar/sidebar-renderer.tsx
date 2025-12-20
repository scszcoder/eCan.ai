  /**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { useCallback, useContext, useEffect, useMemo, startTransition, useRef, useState } from 'react';

import { PlaygroundEntityContext, useRefresh, useClientContext } from '@flowgram.ai/free-layout-editor';

import { FlowNodeMeta } from '../../typings';
import { SidebarContext, IsSidebarContext } from '../../context';
import { SidebarNodeRenderer } from './sidebar-node-renderer';

export const SidebarRenderer = () => {

  const { nodeId, setNodeId } = useContext(SidebarContext);
  // Prevent immediate close after open due to rapid selection/change events
  const lastOpenAtRef = useRef<number>(0);
  const LOCK_MS = 300;
  // Floating panel geometry (right-docked by default)
  const [panelWidth, setPanelWidth] = useState<number>(500);
  const [panelTop, setPanelTop] = useState<number>(40);
  const [panelRight, setPanelRight] = useState<number>(0);
  const [panelHeight, setPanelHeight] = useState<number>(600);
  // Interaction state
  const resizingHRef = useRef<boolean>(false);
  const resizingVRef = useRef<boolean>(false); // bottom edge
  const resizingTopRef = useRef<boolean>(false); // top edge
  const resizingCornerRef = useRef<boolean>(false); // bottom-left
  const resizingCornerRightRef = useRef<boolean>(false); // bottom-right
  const draggingRef = useRef<boolean>(false);
  const startXRef = useRef<number>(0);
  const startYRef = useRef<number>(0);
  const startWRef = useRef<number>(500);
  const startHRef = useRef<number>(600);
  const startTopRef = useRef<number>(40);
  const startRightRef = useRef<number>(0);
  const MIN_W = 360;
  const MAX_W = 1000;
  const MIN_H = 200;
  const { selection, playground, document: playDoc } = useClientContext();
  const refresh = useRefresh();

  // restore persisted geometry on mount
  useEffect(() => {
    try {
      const raw = localStorage.getItem('skill_editor.sidebar_panel_geometry');
      if (raw) {
        const g = JSON.parse(raw);
        if (typeof g.width === 'number') setPanelWidth(Math.max(MIN_W, Math.min(MAX_W, g.width)));
        if (typeof g.top === 'number') setPanelTop(Math.max(0, g.top));
        if (typeof g.right === 'number') setPanelRight(Math.max(0, g.right));
        if (typeof g.height === 'number') setPanelHeight(Math.max(200, g.height));
      }
    } catch {}
  }, []);

  const persistGeometry = useCallback(() => {
    try {
      localStorage.setItem(
        'skill_editor.sidebar_panel_geometry',
        JSON.stringify({ width: panelWidth, top: panelTop, right: panelRight, height: panelHeight })
      );
    } catch {}
  }, [panelWidth, panelTop, panelRight, panelHeight]);

  const handleClose = useCallback(() => {
    // Sidebar delayed closing
    startTransition(() => {
      setNodeId(undefined);
    });
  }, []);

  const node = nodeId ? playDoc.getNode(nodeId) : undefined;

  /**
   * Listen readonly
   */
  useEffect(() => {
    const disposable = playground.config.onReadonlyOrDisabledChange(() => {
      refresh();
    });
    return () => disposable.dispose();
  }, [playground]);
  /**
   * Listen selection but do not auto-close the sidebar. We keep the editor open
   * during runs and only close on explicit user action or when node is disposed.
   */
  useEffect(() => {
    const toDispose = selection.onSelectionChanged(() => {
      try { console.debug('[SidebarRenderer] selection changed, keeping sidebar as-is'); } catch {}
      // Intentionally no auto-close behavior here
    });
    return () => toDispose.dispose();
  }, [selection]);

  // Track when the sidebar is explicitly opened to prevent accidental closes
  useEffect(() => {
    if (nodeId) {
      lastOpenAtRef.current = Date.now();
    }
  }, [nodeId]);
  /**
   * Close when node disposed
   */
  useEffect(() => {
    if (node) {
      const toDispose = node.onDispose(() => {
        setNodeId(undefined);
      });
      return () => toDispose.dispose();
    }
    return () => {};
  }, [node]);

  const visible = useMemo(() => {
    if (!node) {
      return false;
    }
    const { sidebarDisabled = false } = node.getNodeMeta<FlowNodeMeta>();
    // Also hide when editor is readonly to avoid mid-render hook order changes
    return !sidebarDisabled && !playground.config.readonly;
  }, [node, playground.config.readonly]);
  /**
   * Add "key" to rerender the sidebar when the node changes
   */
  const content =
    node && visible ? (
      <PlaygroundEntityContext.Provider key={node.id} value={node}>
        <SidebarNodeRenderer node={node} />
      </PlaygroundEntityContext.Provider>
    ) : null;

  // Global mouse handlers for drag/resize (use window to avoid SSR/document shims)
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (resizingHRef.current || resizingCornerRef.current) {
        const dx = startXRef.current - e.clientX; // drag left increases width
        const next = Math.min(MAX_W, Math.max(MIN_W, startWRef.current + dx));
        setPanelWidth(next);
        try { console.debug('[SidebarRenderer] resizing width ->', next); } catch {}
        e.preventDefault();
        // do not return if also resizing vertically
        if (!resizingCornerRef.current) return;
      }
      if (resizingCornerRightRef.current) {
        const dx = e.clientX - startXRef.current; // drag right increases width
        const next = Math.min(MAX_W, Math.max(MIN_W, startWRef.current + dx));
        setPanelWidth(next);
        try { console.debug('[SidebarRenderer] resizing width (right-corner) ->', next); } catch {}
        e.preventDefault();
        // allow vertical branch below as well if needed
      }
      if (resizingVRef.current || resizingCornerRef.current) {
        const dy = e.clientY - startYRef.current; // drag down increases height
        const vh = window.innerHeight;
        const maxH = Math.max(MIN_H, vh - 20);
        const nextH = Math.min(maxH, Math.max(MIN_H, startHRef.current + dy));
        setPanelHeight(nextH);
        try { console.debug('[SidebarRenderer] resizing height ->', nextH); } catch {}
        e.preventDefault();
        return;
      }
      if (resizingTopRef.current) {
        const dy = e.clientY - startYRef.current; // dragging down increases top, decreases height
        const vh = window.innerHeight;
        const nextTop = Math.max(0, Math.min(vh - 120, startTopRef.current + dy));
        const nextH = Math.max(MIN_H, startHRef.current - dy);
        setPanelTop(nextTop);
        setPanelHeight(nextH);
        try { console.debug('[SidebarRenderer] resizing from top ->', { top: nextTop, height: nextH }); } catch {}
        e.preventDefault();
        return;
      }
      if (draggingRef.current) {
        const dx = e.clientX - startXRef.current;
        const dy = e.clientY - startYRef.current;
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        // Update right and top, clamp within viewport
        const nextRight = Math.max(0, Math.min(vw - 200, startRightRef.current - dx));
        const nextTop = Math.max(0, Math.min(vh - 120, startTopRef.current + dy));
        setPanelRight(nextRight);
        setPanelTop(nextTop);
        e.preventDefault();
        return;
      }
    };
    const onUp = () => {
      if (resizingHRef.current || resizingVRef.current || resizingTopRef.current || resizingCornerRef.current || resizingCornerRightRef.current || draggingRef.current) {
        resizingHRef.current = false;
        resizingVRef.current = false;
        resizingTopRef.current = false;
        resizingCornerRef.current = false;
        resizingCornerRightRef.current = false;
        draggingRef.current = false;
        try { if (window && window.document) { window.document.body.style.userSelect = ''; window.document.body.style.cursor = ''; } } catch {}
        persistGeometry();
      }
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      // Critical: Reset cursor and userSelect on unmount to prevent stuck resize cursor
      try { 
        if (window && window.document && window.document.body) { 
          window.document.body.style.removeProperty('cursor');
          window.document.body.style.removeProperty('user-select');
          window.document.body.style.removeProperty('-webkit-user-select');
          window.document.body.style.removeProperty('-moz-user-select');
          window.document.body.style.removeProperty('-ms-user-select');
        } 
      } catch {}
      // Reset all resize flags
      resizingHRef.current = false;
      resizingVRef.current = false;
      resizingTopRef.current = false;
      resizingCornerRef.current = false;
      resizingCornerRightRef.current = false;
      draggingRef.current = false;
    };
  }, []);

  if (!visible) return null;

  return (
    <IsSidebarContext.Provider value={true}>
      <div
        style={{
          position: 'fixed',
          top: panelTop,
          right: panelRight,
          width: panelWidth,
          height: panelHeight,
          background: '#fff',
          border: '1px solid rgba(82,100,154,0.13)',
          borderRadius: 8,
          boxShadow: '0 6px 18px rgba(0,0,0,0.12)',
          zIndex: 1000,
          pointerEvents: 'auto',
        }}
      >
        {/* Left edge resize overlay (layout-neutral) */}
        <div
          role="separator"
          aria-orientation="vertical"
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            width: 14,
            height: '100%',
            cursor: 'col-resize',
            zIndex: 1500,
            pointerEvents: 'auto',
            background: 'linear-gradient(to right, rgba(0,0,0,0.05), rgba(0,0,0,0))',
          }}
          onMouseDown={(e) => {
            resizingHRef.current = true;
            startXRef.current = e.clientX;
            startWRef.current = panelWidth;
            try { if (window && window.document) { window.document.body.style.userSelect = 'none'; window.document.body.style.cursor = 'col-resize'; } } catch {}
            e.preventDefault();
          }}
          onMouseEnter={() => { try { if (window && window.document) { window.document.body.style.cursor = 'col-resize'; } } catch {} }}
          onMouseLeave={() => { try { if (!resizingHRef.current && window && window.document) { window.document.body.style.cursor = ''; } } catch {} }}
        />
        {/* Bottom edge resize overlay for vertical resizing (top-most) */}
        <div
          role="separator"
          aria-orientation="horizontal"
          style={{
            position: 'absolute',
            left: 0,
            bottom: 0,
            height: 28,
            width: '100%',
            cursor: 'ns-resize',
            zIndex: 1500,
            pointerEvents: 'auto',
            background: 'linear-gradient(to top, rgba(0,0,0,0.06), rgba(0,0,0,0))',
          }}
          onMouseDown={(e) => {
            resizingVRef.current = true;
            startYRef.current = e.clientY;
            startHRef.current = panelHeight;
            try { if (window && window.document) { window.document.body.style.userSelect = 'none'; window.document.body.style.cursor = 'ns-resize'; } } catch {}
            e.preventDefault();
          }}
          onMouseEnter={() => { try { if (window && window.document) { window.document.body.style.cursor = 'ns-resize'; } } catch {} }}
          onMouseLeave={() => { try { if (!resizingVRef.current && window && window.document) { window.document.body.style.cursor = ''; } } catch {} }}
        />
        {/* Bottom-left corner resize overlay for both directions */}
        <div
          style={{
            position: 'absolute',
            left: 0,
            bottom: 0,
            width: 20,
            height: 20,
            cursor: 'nwse-resize',
            zIndex: 1501,
            pointerEvents: 'auto',
            background: 'linear-gradient(45deg, rgba(0,0,0,0.04), rgba(0,0,0,0))',
          }}
          onMouseDown={(e) => {
            resizingCornerRef.current = true;
            startXRef.current = e.clientX;
            startYRef.current = e.clientY;
            startWRef.current = panelWidth;
            startHRef.current = panelHeight;
            try { if (window && window.document) { window.document.body.style.userSelect = 'none'; window.document.body.style.cursor = 'nwse-resize'; } } catch {}
            e.preventDefault();
          }}
        />
        {/* Bottom-right corner resize overlay for both directions */}
        <div
          style={{
            position: 'absolute',
            right: 0,
            bottom: 0,
            width: 20,
            height: 20,
            cursor: 'nesw-resize',
            zIndex: 1501,
            pointerEvents: 'auto',
            background: 'linear-gradient(135deg, rgba(0,0,0,0.04), rgba(0,0,0,0))',
          }}
          onMouseDown={(e) => {
            resizingCornerRightRef.current = true;
            startXRef.current = e.clientX;
            startYRef.current = e.clientY;
            startWRef.current = panelWidth;
            startHRef.current = panelHeight;
            try { if (window && window.document) { window.document.body.style.userSelect = 'none'; window.document.body.style.cursor = 'nesw-resize'; } } catch {}
            e.preventDefault();
          }}
        />
        {/* Panel content: flex column to avoid horizontal displacement */}
        <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          {/* Header (draggable) */}
          <div
            style={{
              height: 28,
              background: '#fff',
              borderBottom: '1px solid rgba(82,100,154,0.13)',
              borderTopLeftRadius: 8,
              borderTopRightRadius: 8,
              cursor: 'move',
              boxShadow: '0 2px 6px rgba(0,0,0,0.06)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0 8px'
            }}
            onMouseDown={(e) => {
              draggingRef.current = true;
              startXRef.current = e.clientX;
              startYRef.current = e.clientY;
              startTopRef.current = panelTop;
              startRightRef.current = panelRight;
              try { if (window && window.document) { window.document.body.style.userSelect = 'none'; } } catch {}
              e.preventDefault();
            }}
          >
            <div style={{ fontSize: 12, color: '#333', fontWeight: 600, pointerEvents: 'none' }}>{node?.data?.title || node?.type || 'Node'}</div>
            <button
              type="button"
              onMouseDown={(e) => e.stopPropagation()}
              onClick={() => setNodeId(undefined)}
              style={{
                fontSize: 12,
                color: '#333',
                background: '#f5f5f5',
                border: '1px solid #d9d9d9',
                borderRadius: 4,
                padding: '2px 6px',
                cursor: 'pointer'
              }}
            >Close</button>
          </div>
          {/* Body */}
          <div style={{ flex: 1, minHeight: 0, minWidth: 0, boxSizing: 'border-box', padding: '8px 12px 28px 12px', overflow: 'auto' }}>
            <div style={{ width: '100%', boxSizing: 'border-box' }}>
              {content}
            </div>
          </div>
        </div>
      </div>
    </IsSidebarContext.Provider>
  );
}
