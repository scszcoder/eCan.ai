import React, { useCallback, useRef, useEffect, useMemo } from 'react';
import type { editor } from 'monaco-editor';
import Editor, { OnChange, loader } from '@monaco-editor/react';
import { CodeEditorComponentProps } from './types';
import { editorStyles } from './styles';
import { DEFAULT_EDITOR_HEIGHT, DEFAULT_EDITOR_OPTIONS, getPreviewModeOptions } from './config';
import ReactDOM from 'react-dom';

// Configure Monaco to use local files
/*
loader.config({
  paths: {
    vs: '/monaco-editor/vs'
  }
});
*/
// Configure Monaco worker
if (typeof window !== 'undefined') {
  (window as any).MonacoEnvironment = {
    getWorkerUrl: function (_moduleId: string, _label: string) {
      return '/monaco-editor/vs/base/worker/workerMain.js';
    }
  };
}

// Add语言ToggleFunction
export const setMonacoLanguage = (language: 'en' | 'zh-cn') => {
  loader.config({
    'vs/nls': {
      availableLanguages: {
        '*': language
      }
    }
  });
};

/**
 * CodeEditor component for displaying and editing code
 *
 * Features:
 * - Monaco Editor integration
 * - Preview/Edit modes
 * - Modal-based editing
 * - Keyboard shortcuts (Esc to close)
 * - Customizable styling
 */
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
  // Refs
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);

  // Event handlers
  const handleCurrentOk = useCallback(() => {
    handleOk?.();
    onVisibleChange?.(false);
  }, [handleOk, onVisibleChange]);

  const handleCurrentCancel = useCallback(() => {
    handleCancel?.();
    onVisibleChange?.(false);
  }, [handleCancel, onVisibleChange]);

  const handleChange: OnChange = useCallback((value) => {
    onChange?.(value || '');
  }, [onChange]);

  const handleEditorDidMount = useCallback((editor: editor.IStandaloneCodeEditor) => {
    editorRef.current = editor;
    editor.setValue(value);
    editor.layout();
    onEditorDidMount?.(editor);
  }, [value, onEditorDidMount]);

  // Editor configuration
  const editorOptions = useMemo(() => {
    const baseOptions = { ...DEFAULT_EDITOR_OPTIONS, ...externalOptions };
    return mode === 'preview' ? getPreviewModeOptions(baseOptions) : baseOptions;
  }, [mode, externalOptions]);

  // Effects
  useEffect(() => {
    const handleEscKey = (event: KeyboardEvent) => {
      if (visible && event.key === 'Escape') {
        handleCurrentCancel();
      }
    };

    document.addEventListener('keydown', handleEscKey);
    return () => document.removeEventListener('keydown', handleEscKey);
  }, [visible, handleCurrentCancel]);

  useEffect(() => {
    if (editorRef.current && editorRef.current.getValue() !== value) {
      editorRef.current.setValue(value);
      editorRef.current.layout();
    }
  }, [value]);

  // Render editor content
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
        loading={<div>Loading editor...</div>}
      />
    </div>
  );

  // Render modes
  if (mode === 'preview') {
    return editorContent;
  }

  if (!visible) {
    return null;
  }

  // Render modal with portal
  return ReactDOM.createPortal(
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
    </div>,
    document.body
  );
};
