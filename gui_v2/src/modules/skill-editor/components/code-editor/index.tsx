import React, { useCallback, useRef, useEffect, useMemo } from 'react';
import { MonacoEditor } from '@/modules/monaco-editor';
import { DEFAULT_EDITOR_OPTIONS } from '@/modules/monaco-editor/config/editor.config';
import type { SupportedLanguage } from '@/modules/monaco-editor/config/editor.config';
import type { IStandaloneCodeEditor } from '@/modules/monaco-editor';
import { CodeEditorComponentProps } from './types';
import { editorStyles } from './styles';
import { DEFAULT_EDITOR_HEIGHT, getPreviewModeOptions } from './config';

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
  const editorRef = useRef<IStandaloneCodeEditor | null>(null);

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

  const handleEditorDidMount = useCallback((editor: IStandaloneCodeEditor) => {
    editorRef.current = editor;
    editor.setValue(value);
    editor.layout();
    onEditorDidMount?.(editor);
  }, [value, onEditorDidMount]);

  const editorContent = (
    <MonacoEditor
      value={value}
      language={language as SupportedLanguage}
      onChange={onChange}
      options={editorOptions}
      className={className}
      style={{
        height,
        width: '100%',
        border: '1px solid var(--semi-color-border)',
        borderRadius: '4px',
        overflow: 'hidden',
        ...style
      }}
      onEditorDidMount={handleEditorDidMount}
    />
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
