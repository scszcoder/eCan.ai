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
  const resizingCornerRef = useRef<boolean>(false);
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
  const { selection, playground, document } = useClientContext();
  const refresh = useRefresh();
  const handleClose = useCallback(() => {
    // Sidebar delayed closing
    startTransition(() => {
      setNodeId(undefined);
    });
  }, []);
  const node = nodeId ? document.getNode(nodeId) : undefined;
  /**
   * Listen readonly
   */
  useEffect(() => {
    const disposable = playground.config.onReadonlyOrDisabledChange(() => {
      // Do not auto-close the sidebar here; readonly/disabled flips can be transient
      refresh();
    });
    return () => disposable.dispose();
  }, [playground]);
  /**
   * Listen selection
   */
  useEffect(() => {
    const toDispose = selection.onSelectionChanged(() => {
      // If no node is selected, close the sidebar
      if (selection.selection.length === 0) {
        const now = Date.now();
        if (now - lastOpenAtRef.current > LOCK_MS) {
          handleClose();
        }
        return;
      }
      // If exactly one node is selected, sync the sidebar to that node instead of closing
      if (selection.selection.length === 1) {
        const sel = selection.selection[0];
        if (sel && sel.id !== nodeId) {
          startTransition(() => setNodeId(sel.id));
          lastOpenAtRef.current = Date.now();
        }
        return;
      }
      // For multi-selection, close by default
      const now = Date.now();
      if (now - lastOpenAtRef.current > LOCK_MS) {
        handleClose();
      }
    });
    return () => toDispose.dispose();
  }, [selection, handleClose, nodeId]);
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
    return !sidebarDisabled;
  }, [node]);

  if (playground.config.readonly) {
    return null;
  }
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
      if (resizingHRef.current || resizingVRef.current || resizingTopRef.current || resizingCornerRef.current || draggingRef.current) {
        resizingHRef.current = false;
        resizingVRef.current = false;
        resizingTopRef.current = false;
        resizingCornerRef.current = false;
        draggingRef.current = false;
        if (typeof document !== 'undefined') {
          document.body.style.userSelect = '';
          document.body.style.cursor = '';
        }
      }
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
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
        {/* Outer left-edge resize overlay to ensure reliable hit area */}
        <div
          role="separator"
          aria-orientation="vertical"
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            width: 16,
            height: '100%',
            cursor: 'col-resize',
            zIndex: 5,
            pointerEvents: 'auto',
            // subtle visual indicator
            background: 'linear-gradient(to right, rgba(0,0,0,0.02), rgba(0,0,0,0))',
          }}
          onMouseDown={(e) => {
            resizingHRef.current = true;
            startXRef.current = e.clientX;
            startWRef.current = panelWidth;
            if (typeof document !== 'undefined') {
              document.body.style.userSelect = 'none';
              document.body.style.cursor = 'col-resize';
            }
            e.preventDefault();
          }}
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
            zIndex: 200000,
            pointerEvents: 'auto',
            background: 'linear-gradient(to top, rgba(0,0,0,0.06), rgba(0,0,0,0))',
          }}
          onMouseDown={(e) => {
            resizingVRef.current = true;
            startYRef.current = e.clientY;
            startHRef.current = panelHeight;
            if (typeof document !== 'undefined') {
              document.body.style.userSelect = 'none';
              document.body.style.cursor = 'ns-resize';
            }
            e.preventDefault();
          }}
          onMouseEnter={() => { try { if (typeof document !== 'undefined') document.body.style.cursor = 'ns-resize'; } catch {} }}
          onMouseLeave={() => { try { if (!resizingVRef.current && typeof document !== 'undefined') document.body.style.cursor = ''; } catch {} }}
        />
        {/* Top edge resize overlay for vertical resizing (top-most) */}
        <div
          role="separator"
          aria-orientation="horizontal"
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            height: 24,
            width: '100%',
            cursor: 'ns-resize',
            zIndex: 1002,
            pointerEvents: 'auto',
            background: 'linear-gradient(to bottom, rgba(0,0,0,0.06), rgba(0,0,0,0))',
          }}
          onMouseDown={(e) => {
            resizingTopRef.current = true;
            startYRef.current = e.clientY;
            startHRef.current = panelHeight;
            startTopRef.current = panelTop;
            if (typeof document !== 'undefined') {
              document.body.style.userSelect = 'none';
              document.body.style.cursor = 'ns-resize';
            }
            e.preventDefault();
          }}
          onMouseEnter={() => { try { if (typeof document !== 'undefined') document.body.style.cursor = 'ns-resize'; } catch {} }}
          onMouseLeave={() => { try { if (!resizingTopRef.current && typeof document !== 'undefined') document.body.style.cursor = ''; } catch {} }}
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
            zIndex: 200001,
            pointerEvents: 'auto',
            background: 'linear-gradient(45deg, rgba(0,0,0,0.04), rgba(0,0,0,0))',
          }}
          onMouseDown={(e) => {
            resizingCornerRef.current = true;
            startXRef.current = e.clientX;
            startYRef.current = e.clientY;
            startWRef.current = panelWidth;
            startHRef.current = panelHeight;
            if (typeof document !== 'undefined') {
              document.body.style.userSelect = 'none';
              document.body.style.cursor = 'nwse-resize';
            }
            e.preventDefault();
          }}
        />
        <div
          style={{
            position: 'absolute',
            inset: 0,
            pointerEvents: 'auto',
            background: 'transparent',
          }}
        >
          {/* Resizable & scrollable content container */}
          <div
            style={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              left: 0,
              right: 0,
              background: 'transparent',
            }}
          >
            {/* The actual panel */}
            <div
              style={{
                position: 'absolute',
                top: 0,
                right: 0,
                bottom: 0,
                left: 0,
                marginLeft: 0,
                background: 'transparent',
              }}
            >
              {/* Visible header for dragging */}
              <div
                style={{
                  height: 28,
                  background: '#fff',
                  borderBottom: '1px solid rgba(82,100,154,0.13)',
                  borderTopLeftRadius: 8,
                  borderTopRightRadius: 8,
                  cursor: 'move',
                  boxShadow: '0 2px 6px rgba(0,0,0,0.06)',
                }}
                onMouseDown={(e) => {
                  draggingRef.current = true;
                  startXRef.current = e.clientX;
                  startYRef.current = e.clientY;
                  startTopRef.current = panelTop;
                  startRightRef.current = panelRight;
                  if (typeof document !== 'undefined') document.body.style.userSelect = 'none';
                  e.preventDefault();
                }}
              />
              {/* Left edge resize handle (inner) */}
              <div
                role="separator"
                aria-orientation="vertical"
                style={{
                  position: 'absolute',
                  left: 0,
                  top: 28,
                  width: 8,
                  bottom: 0,
                  cursor: 'col-resize',
                  zIndex: 3,
                }}
                onMouseDown={(e) => {
                  resizingHRef.current = true;
                  startXRef.current = e.clientX;
                  startWRef.current = panelWidth;
                  if (typeof document !== 'undefined') document.body.style.userSelect = 'none';
                  e.preventDefault();
                }}
              />

              {/* Panel body */}
              <div
                style={{
                  position: 'absolute',
                  top: 28,
                  left: 0,
                  right: 0,
                  bottom: 0,
                  paddingBottom: 28, // keep bottom edge clear for resize overlay
                  paddingTop: 4,
                  background: 'transparent',
                }}
              >
                {content}
              </div>
            </div>
          </div>
        </div>
      </div>
    </IsSidebarContext.Provider>
  );
}
