/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { EditorRenderer, FreeLayoutEditorProvider, useService, WorkflowDocument, WorkflowLinesManager, CommandService, usePlayground } from '@flowgram.ai/free-layout-editor';
import { useEffect, useMemo, useRef } from 'react';
import React from 'react';

import '@flowgram.ai/free-layout-editor/index.css';
import './styles/index.css';
import { nodeRegistries } from './nodes';
import { initialData } from './initial-data';
import { useEditorProps } from './hooks';
import { Tools } from './components/tools';
import { SidebarProvider, SidebarRenderer } from './components/sidebar';
import { FlowDocumentJSON } from './typings';
import emptyFlowData from './data/empty-flow.json';
import { useSkillInfoStore } from './stores/skill-info-store';
import { createSkillInfo } from './typings/skill-info';
import { NodeInfoDisplay } from './components/node-info-display';
import { useSimpleAutoLoad } from './hooks/useAutoLoadRecentFile';
import { RouteFileLoader } from './components/RouteFileLoader';
import { FilePathDisplay } from './components/file-path-display';
import { useUnsavedChangesTracker } from './hooks/useUnsavedChangesTracker';
import { useDragAndDrop } from './hooks/useDragAndDrop';
import styled from 'styled-components';
import { useSheetsStore } from './stores/sheets-store';
import { SheetsTabBar } from './components/tabs/SheetsTabBar';
import { SheetsMenu } from './components/menu/SheetsMenu';
import { ActiveSheetBinder } from './components/tabs/ActiveSheetBinder';
import { RunningNodeNavigator } from './components/tabs/RunningNodeNavigator';
import { isValidationDisabled } from './services/validation-config';
import { useAutoSave } from './stores/editor-auto-save-store';
import { BreakpointBinder } from './components/runtime/BreakpointBinder';

const EditorContainer = styled.div`
  position: relative;
  width: 100%;
  height: 100%;
`;

const SkillNameLabel = styled.div`
  position: absolute;
  top: 10px;
  left: 10px;
  background-color: rgba(255, 255, 255, 0.8);
  padding: 5px 10px;
  border-radius: 5px;
  font-weight: bold;
  z-index: 10;
  pointer-events: none; /* Make it non-interactive */
  color: #333; /* Add a dark color for the text */
`;

export const Editor = () => {
  const emptyData: FlowDocumentJSON = emptyFlowData;

  // ProductionEnvironment不Load初始Data，DevelopmentEnvironment根据Configuration决定
  const shouldLoadInitialData = process.env.NODE_ENV === 'development' ? true : false;
  const { skillInfo } = useSkillInfoStore();
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);

  // Editor ready state
  const [editorReady, setEditorReady] = React.useState(false);
  const editorReadyRef = useRef(false);
  
  useEffect(() => {
    if (editorReadyRef.current) return;
    editorReadyRef.current = true;
    setEditorReady(true);
  }, []);

  // Track unsaved changes
  useUnsavedChangesTracker();

  // Enable drag-and-drop file support
  useDragAndDrop({
    enabled: true,
    onFileDropped: (filePath, skillInfo) => {
      console.log(`[Editor] File dropped: ${skillInfo.skillName || 'Untitled'} from ${filePath}`);
    },
    onDropError: (error) => {
      console.error('[Editor] Drag-and-drop error:', error.message);
    },
  });

  // Determine the initial document: prefer current skill's workflow if available
  const preferredDoc: FlowDocumentJSON = useMemo(
    () => (skillInfo?.workFlow as FlowDocumentJSON) || (shouldLoadInitialData ? initialData : emptyData),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [skillInfo?.workFlow]
  );

  // Seed the store only once if it's empty
  const seededRef = useRef(false);
  useEffect(() => {
    if (!skillInfo && !seededRef.current) {
      setSkillInfo(createSkillInfo(preferredDoc));
      seededRef.current = true;
    }
  }, [skillInfo, preferredDoc, setSkillInfo]);

  // Visibility: warn when validation is globally disabled
  useEffect(() => {
    try {
      // Force-disable validation at runtime for now
      (window as any).__SKILL_EDITOR_DISABLE_VALIDATION__ = true;
      localStorage.setItem('SKILL_EDITOR_DISABLE_VALIDATION', 'true');
    } catch {}

    if (isValidationDisabled()) {
      console.info('[VALIDATION_DISABLED] Frontend validation is disabled in the skill editor.');
    } else {
      console.warn('[VALIDATION_DISABLED] Attempted to disable validation but flag still false.');
    }
  }, []);

  // Build editor props from the chosen initial document
  const editorProps = useEditorProps(preferredDoc, nodeRegistries);

  // Sheets store: ensure main sheet exists with initial document
  const initMain = useSheetsStore((s) => s.initMain);
  const sheets = useSheetsStore((s) => s.sheets);
  const order = useSheetsStore((s) => s.order);
  const openTabs = useSheetsStore((s) => s.openTabs);
  const activeSheetId = useSheetsStore((s) => s.activeSheetId);
  const openSheet = useSheetsStore((s) => s.openSheet);

  // Get current state for auto-save
  const breakpoints = useSkillInfoStore((state) => state.breakpoints);
  const currentFilePath = useSkillInfoStore((state) => state.currentFilePath);

  // Initialize main sheet once when editor is ready
  const sheetsInitializedRef = useRef(false);
  useEffect(() => {
    if (!editorReady || sheetsInitializedRef.current) return;
    sheetsInitializedRef.current = true;

    // Initialize with preferredDoc (auto-load will override if file is loaded)
    console.log('[Editor] Initializing sheets with preferredDoc');
    initMain(preferredDoc);
    openSheet('main');
  }, [editorReady, preferredDoc, initMain, openSheet]);

  // Memoize sheets state to prevent unnecessary re-renders triggering auto-save
  const sheetsState = useMemo(() => ({
    sheets,
    order,
    openTabs,
    activeSheetId,
  }), [sheets, order, openTabs, activeSheetId]);

  // Stable empty array reference for selectionIds
  const emptySelectionIds = useMemo(() => [], []);

  // Auto-save editor state directly to file
  useAutoSave(
    skillInfo,
    sheetsState,
    breakpoints,
    currentFilePath,
    null, // viewState - can be added later if needed
    emptySelectionIds
  );

  return (
    <EditorContainer>
      <div className="doc-free-feature-overview">
        <SkillEditorErrorBoundary>
          <FreeLayoutEditorProvider {...editorProps}>
            <AnchorProbe />
            {/* Auto-load recent file on startup (must be inside provider for useClientContext) */}
            <AutoLoadHandler />
            {/* Load file from route state if present */}
            <RouteFileLoader />
            {/* Sync the active sheet's document with the editor's WorkflowDocument */}
            <ActiveSheetBinder />
            {/* Ensure breakpoint-stalled nodes still show visuals when no running node is set */}
            <BreakpointBinder />
            <RunningNodeNavigator />
            <SidebarProvider>
              <NodeInfoDisplay />
              <div className="demo-container">
                {/* Sheets toolbar: tab bar and sheets menu */}
                <div style={{ display: 'flex', alignItems: 'center', padding: '4px 8px', gap: 8 }}>
                  <SheetsTabBar />
                  <div style={{ marginLeft: 'auto' }}>
                    <SheetsMenu />
                  </div>
                </div>
                <EditorRenderer className="demo-editor">
                  <FilePathDisplay />
                </EditorRenderer>
              </div>
              <Tools />
              <SidebarRenderer />
            </SidebarProvider>
          </FreeLayoutEditorProvider>
        </SkillEditorErrorBoundary>
      </div>
    </EditorContainer>
  );
};

// AutoLoadHandler - handles auto-loading recent files (must be inside FreeLayoutEditorProvider)
const AutoLoadHandler: React.FC = () => {
  useSimpleAutoLoad();
  return null;
};

// Phase 3: AnchorProbe – gated diagnostics for anchor-side updates
const AnchorProbe: React.FC = () => {
  const documentSvc = useService(WorkflowDocument);
  const linesMgr = useService(WorkflowLinesManager);
  const cmdSvc = useService(CommandService);
  const playground = usePlayground();

  React.useEffect(() => {
    try {
      // Toggle in DevTools: window.__SE_DEBUG_ANCHORS__ = true
      // Then re-select a node or reload to see logs
      // @ts-ignore
      const dbg = (window as any).__SE_DEBUG_ANCHORS__ === true;
      const safeListMethods = (obj: any) => {
        if (!obj) return [];
        return Object.getOwnPropertyNames(Object.getPrototypeOf(obj))
          .filter((k) => typeof (obj as any)[k] === 'function')
          .sort();
      };

      const dump = () => {
        const info = {
          services: {
            document: documentSvc ? {
              type: documentSvc.constructor?.name,
              methods: safeListMethods(documentSvc),
            } : null,
            linesManager: linesMgr ? {
              type: linesMgr.constructor?.name,
              methods: safeListMethods(linesMgr),
            } : null,
            commandService: cmdSvc ? {
              type: cmdSvc.constructor?.name,
              methods: safeListMethods(cmdSvc),
            } : null,
            playground: playground ? {
              type: playground.constructor?.name,
              // Important helpers exposed via config/context
              configMethods: playground.config ? safeListMethods(playground.config) : [],
            } : null,
          },
        };
        // eslint-disable-next-line no-console
        console.log('[SkillEditor][Phase3][Probe] available services/methods', info);
        return info;
      };

      // expose manual trigger
      try {
        (window as any).__SE_DUMP_ANCHORS__ = dump;
        (window as any).__SE_CHECK_COMMANDS__ = () => ({
          portUpdate: !!(cmdSvc as any)?.getCommand?.('workflow.port.updateSide'),
          nodeUpdate: !!(cmdSvc as any)?.getCommand?.('workflow.node.updatePortsSide'),
        });
      } catch {}

      if (dbg) {
        dump();
      }
    } catch (e) {
      // eslint-disable-next-line no-console
      console.warn('[SkillEditor][Phase3][Probe] failed to enumerate services', e);
    }
    return () => {
      try {
        delete (window as any).__SE_DUMP_ANCHORS__;
        delete (window as any).__SE_CHECK_COMMANDS__;
      } catch {}
    };
  }, [documentSvc, linesMgr, cmdSvc, playground]);

  return null;
};


class SkillEditorErrorBoundary extends React.Component<{ children: React.ReactNode }, { hasError: boolean; error?: Error }>{
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error('SkillEditor crashed:', error, info);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 16 }}>
          <h3>Skill Editor encountered an error</h3>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{String(this.state.error?.message || 'Unknown error')}</pre>
        </div>
      );
    }
    return this.props.children as React.ReactElement;
  }
}
