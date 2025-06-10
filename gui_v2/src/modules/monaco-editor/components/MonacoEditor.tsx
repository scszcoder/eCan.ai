import React, { useEffect, useRef, useState } from 'react';
import * as monaco from 'monaco-editor';
import { DEFAULT_EDITOR_OPTIONS } from '../config/editor.config';
import type { SupportedLanguage } from '../config/editor.config';
import { MONACO_WORKER_CONFIG, SUPPORTED_LANGUAGES } from '../config/editor.config';
import { configureLanguages } from '../config/language-features';

interface MonacoEditorProps {
  value: string;
  language: SupportedLanguage;
  onChange?: (value: string) => void;
  options?: monaco.editor.IStandaloneEditorConstructionOptions;
  className?: string;
  style?: React.CSSProperties;
  onEditorDidMount?: (editor: monaco.editor.IStandaloneCodeEditor) => void;
}

// 初始化 Monaco 环境
if (typeof self !== 'undefined' && !self.MonacoEnvironment) {
  self.MonacoEnvironment = MONACO_WORKER_CONFIG;
}

// 注册支持的语言
SUPPORTED_LANGUAGES.forEach(lang => {
  if (!monaco.languages.getLanguages().some(l => l.id === lang)) {
    monaco.languages.register({ id: lang });
  }
});

export const MonacoEditor: React.FC<MonacoEditorProps> = ({
  value,
  language,
  onChange,
  options = {},
  className = '',
  style,
  onEditorDidMount,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const [isInitialized, setIsInitialized] = useState(false);

  // 初始化 Monaco Editor
  useEffect(() => {
    const initializeEditor = async () => {
      if (!containerRef.current || isInitialized) return;

      try {
        // 等待 Monaco Editor 完全加载
        const waitForMonaco = () => {
          if (monaco.languages.typescript) {
            // 配置语言特性
            configureLanguages();
            setIsInitialized(true);
          } else {
            setTimeout(waitForMonaco, 100);
          }
        };

        waitForMonaco();

        // 创建编辑器实例
        editorRef.current = monaco.editor.create(containerRef.current, {
          ...DEFAULT_EDITOR_OPTIONS,
          ...options,
          value,
          language,
        });

        // 监听内容变化
        editorRef.current.onDidChangeModelContent(() => {
          const value = editorRef.current?.getValue() || '';
          onChange?.(value);
        });

        // 调用 onEditorDidMount 回调
        onEditorDidMount?.(editorRef.current);
      } catch (error) {
        console.error('Failed to initialize Monaco Editor:', error);
      }
    };

    initializeEditor();

    // 组件卸载时销毁编辑器
    return () => {
      editorRef.current?.dispose();
    };
  }, [isInitialized, onEditorDidMount]);

  // 更新编辑器内容
  useEffect(() => {
    if (editorRef.current && value !== editorRef.current.getValue()) {
      editorRef.current.setValue(value);
      editorRef.current.layout();
    }
  }, [value]);

  // 更新编辑器语言
  useEffect(() => {
    if (editorRef.current) {
      monaco.editor.setModelLanguage(editorRef.current.getModel()!, language);
    }
  }, [language]);

  return (
    <div 
      ref={containerRef} 
      className={`monaco-editor-container ${className}`} 
      style={{ 
        height: '100%', 
        width: '100%',
        ...style 
      }} 
    />
  );
}; 