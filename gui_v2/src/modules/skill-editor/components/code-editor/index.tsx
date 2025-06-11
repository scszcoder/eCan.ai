import React, { useCallback, useRef, useEffect, useMemo } from 'react';
import type { editor } from 'monaco-editor';
import Editor, { OnChange } from '@monaco-editor/react';
import { CodeEditorComponentProps } from './types';
import { editorStyles } from './styles';
import { DEFAULT_EDITOR_HEIGHT, DEFAULT_EDITOR_OPTIONS, getPreviewModeOptions } from './config';

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
    const baseOptions = { ...DEFAULT_EDITOR_OPTIONS, ...externalOptions };
    return mode === 'preview' ? getPreviewModeOptions(baseOptions) : baseOptions;
  }, [mode, externalOptions]);

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

  const handleEditorDidMount = useCallback((editor: editor.IStandaloneCodeEditor) => {
    editorRef.current = editor;
    editor.setValue(value);
    editor.layout();
    onEditorDidMount?.(editor);
  }, [value, onEditorDidMount]);

  const handleChange: OnChange = useCallback((value) => {
    onChange?.(value || '');
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
