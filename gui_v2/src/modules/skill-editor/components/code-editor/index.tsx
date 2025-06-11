import React, { useCallback, useRef, useEffect, useMemo } from 'react';
import type { editor } from 'monaco-editor';
import Editor, { OnChange, loader } from '@monaco-editor/react';
import { CodeEditorComponentProps, SupportedLanguage } from './types';
import { editorStyles } from './styles';
import { DEFAULT_EDITOR_HEIGHT, DEFAULT_EDITOR_OPTIONS, getPreviewModeOptions } from './config';
import { registerThemes, getCurrentTheme } from './theme';

// // 配置 Monaco Editor 加载器
// loader.config({
//   paths: {
//     vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs'
//   }
// });

// 注册主题
registerThemes();

export const CodeEditor: React.FC<CodeEditorComponentProps> = ({
  value,
  onChange,
  language,
  visible,
  handleOk,
  handleCancel,
  onVisibleChange,
  options: externalOptions,
  mode = 'edit',
  height = DEFAULT_EDITOR_HEIGHT,
  className,
  style,
  onEditorDidMount,
}) => {
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);

  const handleCurrentOk = useCallback(() => {
    handleOk?.();
    onVisibleChange?.(false);
  }, [handleOk, onVisibleChange]);

  const handleCurrentCancel = useCallback(() => {
    handleCancel?.();
    onVisibleChange?.(false);
  }, [handleCancel, onVisibleChange]);

  const editorOptions = useMemo(() => {
    const baseOptions = { 
      ...DEFAULT_EDITOR_OPTIONS, 
      ...externalOptions,
      theme: 'vs-dark'
    };
    return mode === 'preview' ? getPreviewModeOptions(baseOptions) : baseOptions;
  }, [mode, externalOptions]);

  // 监听主题变化
  useEffect(() => {
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.attributeName === 'data-theme') {
          const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
          if (editorRef.current) {
            editorRef.current.updateOptions({
              theme: isDark ? 'vs-dark' : 'vs'
            });
          }
        }
      });
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme']
    });

    return () => {
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    const handleEscKey = (event: KeyboardEvent) => {
      if (visible && event.key === 'Escape') {
        handleCurrentCancel();
      }
    };

    document.addEventListener('keydown', handleEscKey);
    return () => {
      document.removeEventListener('keydown', handleEscKey);
    };
  }, [visible, handleCurrentCancel]);

  useEffect(() => {
    if (editorRef.current) {
      const currentValue = editorRef.current.getValue();
      if (currentValue !== value) {
        editorRef.current.setValue(value);
        editorRef.current.layout();
      }
    }
  }, [value]);

  const handleEditorDidMount = useCallback((editor: editor.IStandaloneCodeEditor) => {
    editorRef.current = editor;
    editor.setValue(value);
    editor.layout();
    
    // 设置初始主题
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    editor.updateOptions({
      theme: isDark ? 'vs-dark' : 'vs'
    });
    
    onEditorDidMount?.(editor);
  }, [value, onEditorDidMount]);

  const handleChange: OnChange = useCallback((value) => {
    if (onChange) {
      onChange(value || '');
    }
  }, [onChange]);

  const editorContent = (
    <div
      className={className}
      style={{
        height,
        width: '100%',
        border: '1px solid var(--semi-color-border)',
        borderRadius: '4px',
        overflow: 'hidden',
        ...style
      }}
    >
      <Editor
        value={value}
        language={language}
        onChange={handleChange}
        options={editorOptions}
        onMount={handleEditorDidMount}
        height="100%"
        width="100%"
        theme="vs-dark"
        beforeMount={(monaco) => {
          // 确保在编辑器挂载前注册主题
          registerThemes();
        }}
      />
    </div>
  );

  if (mode === 'preview') {
    return editorContent;
  }

  if (!visible) {
    return null;
  }

  return (
    <div className="custom-editor-container" style={editorStyles.container}>
      <div className="custom-editor-content" style={editorStyles.content}>
        <div className="custom-editor-header" style={editorStyles.header}>
          <div className="custom-editor-title" style={editorStyles.title}>
            Code Editor
          </div>
          <div 
            className="custom-editor-close" 
            onClick={handleCurrentCancel} 
            style={editorStyles.closeButton}
          >
            ×
          </div>
        </div>
        <div style={editorStyles.editorContainer}>
          {editorContent}
        </div>
        <div className="custom-editor-footer" style={editorStyles.footer}>
          <button 
            onClick={handleCurrentCancel}
            style={{ ...editorStyles.button, ...editorStyles.cancelButton }}
          >
            Cancel
          </button>
          <button 
            onClick={handleCurrentOk}
            style={{ ...editorStyles.button, ...editorStyles.okButton }}
          >
            OK
          </button>
        </div>
      </div>
    </div>
  );
};
