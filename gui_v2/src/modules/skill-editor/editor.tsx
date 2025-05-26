import { EditorRenderer, FreeLayoutEditorProvider } from '@flowgram.ai/free-layout-editor';

import '@flowgram.ai/free-layout-editor/index.css';
import './styles/index.css';
import { nodeRegistries } from './nodes';
import { initialData } from './initial-data';
import { useEditorProps } from './hooks';
import { Tools } from './components/tools';
import { SidebarProvider, SidebarRenderer } from './components/sidebar';
import { FlowDocumentJSON } from './typings';

export const SkEditor = () => {
  const emptyData: FlowDocumentJSON = {
    nodes: [],
    edges: []
  };

  // 生产环境不加载初始数据，开发环境根据配置决定
  const shouldLoadInitialData = process.env.NODE_ENV === 'development' ? true : false;
  const editorProps = useEditorProps(shouldLoadInitialData ? initialData : emptyData, nodeRegistries);

  return (
    <div className="doc-free-feature-overview">
      <FreeLayoutEditorProvider {...editorProps}>
        <SidebarProvider>
          <div className="demo-container">
            <EditorRenderer className="demo-editor" />
          </div>
          <Tools />
          <SidebarRenderer />
        </SidebarProvider>
      </FreeLayoutEditorProvider>
    </div>
  );
};
