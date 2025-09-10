/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { EditorRenderer, FreeLayoutEditorProvider } from '@flowgram.ai/free-layout-editor';
import { useState } from 'react';

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
import styled from 'styled-components';

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
  const editorProps = useEditorProps(shouldLoadInitialData ? initialData : emptyData, nodeRegistries);

  // 初始化时生成 SkillInfo
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);
  const data = shouldLoadInitialData ? initialData : emptyData;
  // 只在首次挂载时生成一次
  useState(() => {
    setSkillInfo(createSkillInfo(data));
    return undefined;
  });

  const { skillInfo } = useSkillInfoStore();

  return (
    <EditorContainer>
      <div className="doc-free-feature-overview">
        <FreeLayoutEditorProvider {...editorProps}>
          <SidebarProvider>
            <NodeInfoDisplay />
            <div className="demo-container">
              <EditorRenderer className="demo-editor">
                {skillInfo?.skillName && <SkillNameLabel>{skillInfo.skillName}</SkillNameLabel>}
              </EditorRenderer>
            </div>
            <Tools />
            <SidebarRenderer />
          </SidebarProvider>
        </FreeLayoutEditorProvider>
      </div>
    </EditorContainer>
  );
};
