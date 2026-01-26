/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { EditorRenderer, FreeLayoutEditorProvider, useService, WorkflowDocument, WorkflowLinesManager, CommandService, usePlayground } from '@flowgram.ai/free-layout-editor';
import { EditorBridge } from './components/EditorBridge';
// import { DockedPanelLayer } from '@flowgram.ai/panel-manager-plugin';
import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import React from 'react';
import { ChatPanel, FloatingToggleButton, ResizableDivider } from './components/chat-panel';

// Error boundary specifically for ChatPanel to isolate its crashes
class ChatPanelErrorBoundary extends React.Component<{ children: React.ReactNode }, { hasError: boolean; error?: Error }> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ChatPanelErrorBoundary] ChatPanel crashed:', error, info);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 16, background: '#1e293b', color: '#ef4444', minWidth: 280 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Chat Panel Error</div>
          <div style={{ fontSize: 12, color: '#94a3b8' }}>
            {this.state.error?.message || 'An unknown error occurred'}
          </div>
          <button
            onClick={() => this.setState({ hasError: false, error: undefined })}
            style={{ marginTop: 12, padding: '6px 12px', cursor: 'pointer' }}
          >
            Try Again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

import '@flowgram.ai/free-layout-editor/index.css';
import './styles/index.css';
import { nodeRegistries } from './nodes';
import { initialData } from './initial-data';
import { useEditorProps } from './hooks';
import { Tools } from './components/tools';
import { OpenPickerModal } from './components/tools/open-picker-modal';
import { SidebarProvider, SidebarRenderer } from './components/sidebar';
import { FlowDocumentJSON } from './typings';
import emptyFlowData from './data/empty-flow.json';
import { useSkillInfoStore } from './stores/skill-info-store';
import { createSkillInfo } from './typings/skill-info';
import { NodeInfoDisplay } from './components/node-info-display';
import { useAutoLoadRecentFile } from './hooks/useAutoLoadRecentFile';
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
import { useLocation } from 'react-router-dom';
import { PageRefreshManager } from '../../services/events/PageRefreshManager';
import { IPCAPI } from '../../services/ipc/api';
import { isWebPlatform } from '../../config/platform';
import { useUserStore } from '../../stores/userStore';
import { eventBus } from '@/utils/eventBus';

const EditorContainer = styled.div`
  position: relative;
  width: 100%;
  height: 100%;
`;

const SplitLayoutContainer = styled.div`
  display: flex;
  width: 100%;
  height: 100%;
  position: relative;
`;

const RightPanelContainer = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  position: relative;
`;

const DEFAULT_CHAT_WIDTH = 360;
const MIN_CHAT_WIDTH = 280;
const MAX_CHAT_WIDTH = 600;

export const Editor = () => {
  const emptyData: FlowDocumentJSON = emptyFlowData;

  // ProductionEnvironment不Load初始Data，DevelopmentEnvironment根据Configuration决定
  const shouldLoadInitialData = process.env.NODE_ENV === 'development' ? true : false;
  const { skillInfo } = useSkillInfoStore();
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);
  const username = useUserStore((state) => state.username);

  // Editor ready state
  const [editorReady, setEditorReady] = React.useState(false);
  const editorReadyRef = useRef(false);

  // Chat panel state
  const [chatCollapsed, setChatCollapsed] = useState(true);
  const [chatWidth, setChatWidth] = useState(DEFAULT_CHAT_WIDTH);

  const handleChatToggle = useCallback(() => {
    setChatCollapsed(prev => !prev);
  }, []);

  const handleChatResize = useCallback((delta: number) => {
    setChatWidth(prev => {
      const newWidth = prev + delta;
      return Math.max(MIN_CHAT_WIDTH, Math.min(MAX_CHAT_WIDTH, newWidth));
    });
  }, []);

  useEffect(() => {
    if (editorReadyRef.current) return;
    editorReadyRef.current = true;
    setEditorReady(true);
  }, []);

  // Load context from backend - only run ONCE on mount
  // IMPORTANT: We intentionally do NOT depend on skillInfo changes here.
  // When loadFlowgram() calls setSkillInfo(), we must NOT re-run this effect
  // because it would cause a feedback loop that destabilizes the FreeLayoutEditorProvider.
  const contextLoadedRef = useRef(false);
  
  useEffect(() => {
    // TEMPORARILY DISABLED: Testing if context loading causes the crash
    console.log('[SkillEditor] Context loading DISABLED for testing');
    return;
    
    if (!isWebPlatform()) return;
    if (!username) {
      console.warn('[SkillEditor] Cannot load context: userId missing');
      return;
    }
    
    // Only load context ONCE per editor mount
    if (contextLoadedRef.current) {
      console.log('[SkillEditor] Context already loaded, skipping');
      return;
    }
    contextLoadedRef.current = true;

    // Capture skillInfo at the time of initial load
    const currentSkillInfo = skillInfo;
    
    const input: Record<string, any> = { userId: username };
    if (currentSkillInfo?.skillName) {
      input.skillNames = [currentSkillInfo.skillName];
    }
    if (currentSkillInfo?.skillId) {
      input.skillIds = [currentSkillInfo.skillId];
    }

    console.log('[SkillEditor] Loading context with input:', input);

    IPCAPI.getInstance()
      .executeRequest<{ items: any[] }>('skill_editor.context.load', input)
      .then((response) => {
        if (response.success) {
          const items = response.data?.items ?? [];
          console.log('[SkillEditor] Loaded contexts:', items);
          eventBus.emit('skill_editor:context:loaded', {
            items,
            skillId: currentSkillInfo?.skillId,
            skillName: currentSkillInfo?.skillName,
          });
        } else {
          console.warn('[SkillEditor] Failed to load contexts:', response.error);
        }
      })
      .catch((error) => {
        console.error('[SkillEditor] Error loading contexts:', error);
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [username]); // Only depend on username - NOT skillInfo to prevent feedback loop

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
  // IMPORTANT: Use a ref to capture initial value ONCE to prevent provider remounting
  // when skillInfo.workFlow changes (which would cause React error #321)
  const initialDocRef = useRef<FlowDocumentJSON | null>(null);
  if (initialDocRef.current === null) {
    initialDocRef.current = (skillInfo?.workFlow as FlowDocumentJSON) || (shouldLoadInitialData ? initialData : emptyData);
  }
  const preferredDoc: FlowDocumentJSON = initialDocRef.current;

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
  const previewMode = useSkillInfoStore((state) => state.previewMode);

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
  // Use JSON.stringify to create a stable fingerprint that detects deep changes
  // Include node data snippets to detect hFlip and other data changes
  const sheetsFingerprint = useMemo(() => {
    return JSON.stringify({
      sheetIds: Object.keys(sheets),
      sheetDocs: Object.entries(sheets).map(([id, s]) => ({
        id,
        name: s.name,
        nodeCount: s.document?.nodes?.length ?? 0,
        edgeCount: s.document?.edges?.length ?? 0,
        // Include data snippets to detect hFlip and other changes
        nodesData: s.document?.nodes?.map((n: any) => ({
          id: n.id,
          dataSnippet: n.data ? JSON.stringify(n.data).slice(0, 100) : '',
        })),
      })),
    });
  }, [sheets]);

  const sheetsState = useMemo(() => ({
    sheets,
    order,
    openTabs,
    activeSheetId,
  }), [sheets, order, openTabs, activeSheetId, sheetsFingerprint]);

  // Stable empty array reference for selectionIds
  const emptySelectionIds = useMemo(() => [], []);

  // Auto-save editor state directly to file
  useAutoSave(
    skillInfo,
    sheetsState,
    breakpoints,
    previewMode ? null : currentFilePath,
    null, // viewState - can be added later if needed
    emptySelectionIds
  );


  console.log('[Editor] Rendering Editor component', { editorReady, chatCollapsed, activeSheetId, skillInfo: !!skillInfo });
  
  // Log when component is about to unmount (for debugging)
  useEffect(() => {
    console.log('[Editor] Editor component MOUNTED');
    return () => {
      console.log('[Editor] Editor component UNMOUNTING - this should NOT happen during normal operation');
    };
  }, []);
  
  return (
    <EditorContainer>
      <SplitLayoutContainer>
        {/* Left side: Collapsible Chat Panel */}
        {console.log('[Editor] About to render ChatPanel')}
        <ChatPanelErrorBoundary>
          <ChatPanel
            isCollapsed={chatCollapsed}
            onToggle={handleChatToggle}
            width={chatWidth}
          />
        </ChatPanelErrorBoundary>
        
        {/* Resizable divider between chat and editor */}
        <ResizableDivider
          onResize={handleChatResize}
          isVisible={!chatCollapsed}
        />
        
        {/* Right side: Canvas + Console */}
        {console.log('[Editor] About to render RightPanelContainer')}
        <RightPanelContainer>
          <div className="doc-free-feature-overview">
            <SkillEditorErrorBoundary>
              {console.log('[Editor] About to render FreeLayoutEditorProvider')}
              <FreeLayoutEditorProvider {...editorProps}>
                <EditorBridge />
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
                {console.log('[Editor] About to render SidebarProvider')}
                <SidebarProvider>
                  <NodeInfoDisplay />
                  <div className="demo-container">
                    {/* Sheets toolbar: tab bar and sheets menu */}
                    <div style={{ display: 'flex', alignItems: 'center', padding: '4px 8px', gap: 8, flexShrink: 0, minHeight: 48 }}>
                      {console.log('[Editor] About to render SheetsTabBar')}
                      <SheetsTabBar />
                      <div style={{ marginLeft: 'auto' }}>
                        {console.log('[Editor] About to render SheetsMenu')}
                        <SheetsMenu />
                      </div>
                    </div>
                    
                    {/* DockedPanelLayer for ProblemPanel etc - needs flex:1 to fill remaining space */}
                    <div style={{ flex: 1, position: 'relative', minHeight: 0 }}>
                      {/* <DockedPanelLayer> */}
                      <EditorRenderer className="demo-editor">
                        <FilePathDisplay />
                      </EditorRenderer>
                      {/* </DockedPanelLayer> */}
                    </div>
                  </div>
                  <Tools />
                  <SidebarRenderer />
                </SidebarProvider>
              </FreeLayoutEditorProvider>
            </SkillEditorErrorBoundary>
          </div>
          
          {/* Floating toggle button on the left edge of the right panel */}
          <FloatingToggleButton
            isCollapsed={chatCollapsed}
            onClick={handleChatToggle}
            leftOffset={0}
          />
        </RightPanelContainer>
      </SplitLayoutContainer>
      
      {/* Open Skill Picker Modal - rendered via portal, completely isolated from flowgram context */}
      <OpenPickerModal />
    </EditorContainer>
  );
};

// AutoLoadHandler - handles auto-loading recent files (must be inside FreeLayoutEditorProvider)
const AutoLoadHandler: React.FC = () => {
  const location = useLocation();
  const currentFilePath = useSkillInfoStore((state) => state.currentFilePath);

  const state = location.state as { filePath?: string } | null;
  const hasRouteFile = !!state?.filePath;

  const isReloadSkillEditor = PageRefreshManager.isReloadSkillEditor();

  const shouldAutoLoad = !currentFilePath && (!hasRouteFile || isReloadSkillEditor);
  useAutoLoadRecentFile({ enabled: shouldAutoLoad });
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
