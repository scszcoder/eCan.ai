/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { EditorRenderer, FreeLayoutEditorProvider, useClientContext } from '@flowgram.ai/free-layout-editor';
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
import { FilePathDisplay } from './components/file-path-display';
import { useUnsavedChangesTracker } from './hooks/useUnsavedChangesTracker';
import { useDragAndDrop } from './hooks/useDragAndDrop';
import styled from 'styled-components';
import { useSheetsStore } from './stores/sheets-store';
import { SheetsTabBar } from './components/tabs/SheetsTabBar';
import { SheetsMenu } from './components/menu/SheetsMenu';
import { ActiveSheetBinder } from './components/tabs/ActiveSheetBinder';
import { isValidationDisabled } from './services/validation-config';

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

  // 生产环境不加载初始数据，开发环境根据配置决定
  const shouldLoadInitialData = process.env.NODE_ENV === 'development' ? true : false;
  const { skillInfo } = useSkillInfoStore();
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);

  // Auto-load the most recent file on startup
  useSimpleAutoLoad();

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
      console.warn('[VALIDATION_DISABLED] Frontend validation is disabled in the skill editor.');
    } else {
      console.warn('[VALIDATION_DISABLED] Attempted to disable validation but flag still false.');
    }
  }, []);

  // Build editor props from the chosen initial document
  const editorProps = useEditorProps(preferredDoc, nodeRegistries);

  // Sheets store: ensure main sheet exists with initial document
  const initMain = useSheetsStore((s) => s.initMain);
  const activeSheetId = useSheetsStore((s) => s.activeSheetId);
  const openSheet = useSheetsStore((s) => s.openSheet);
  const saveActiveDocument = useSheetsStore((s) => s.saveActiveDocument);
  const getActiveDocument = useSheetsStore((s) => s.getActiveDocument);

  // Initialize main sheet once when skill info is ready
  useEffect(() => {
    // Seed main sheet with preferredDoc so it matches current editor
    initMain(preferredDoc);
    // Ensure main tab is open/active
    openSheet('main');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <EditorContainer>
      <div className="doc-free-feature-overview">
        <SkillEditorErrorBoundary>
          <FreeLayoutEditorProvider {...editorProps}>
            {/* Sync the active sheet's document with the editor's WorkflowDocument */}
            <ActiveSheetBinder />
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
