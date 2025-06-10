import React, { useCallback, useRef, useEffect, useMemo } from 'react';
import { MonacoEditor } from '@/modules/monaco-editor';
import { DEFAULT_EDITOR_OPTIONS } from '@/modules/monaco-editor/config/editor.config';
import type { SupportedLanguage } from '@/modules/monaco-editor/config/editor.config';
import type { IStandaloneEditorConstructionOptions, IStandaloneCodeEditor, CodeEditorProps } from '@/modules/monaco-editor';

export const CodeEditor: React.FC<CodeEditorProps> = ({
  value,
  onChange,
  language,
  visible,
  handleOk,
  handleCancel,
  onVisibleChange,
  options: externalOptions,
  mode = 'edit',
  height = 'calc(100vh - 120px)',
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
    
    if (mode === 'preview') {
      return {
        ...baseOptions,
        readOnly: true,
        lineNumbers: 'off' as const,
        folding: false,
        glyphMargin: false,
        lineDecorationsWidth: 0,
        lineNumbersMinChars: 0,
        renderLineHighlight: 'none' as const,
        overviewRulerBorder: false,
        hideCursorInOverviewRuler: true,
        overviewRulerLanes: 0,
        scrollbar: {
          vertical: 'hidden' as const,
          horizontal: 'hidden' as const
        }
      } as IStandaloneEditorConstructionOptions;
    }
    
    return baseOptions;
  }, [mode, externalOptions]);

  // Add ESC key handler to match Modal's closeOnEsc behavior
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

  // Update editor value when value prop changes
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
    if (onEditorDidMount) {
      onEditorDidMount(editor);
    }
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
    <div 
      className="custom-editor-container"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 1000,
        backgroundColor: 'rgba(0, 0, 0, 0.6)', // Semi Modal overlay background
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        boxSizing: 'border-box'
      }}
    >
      <div 
        className="custom-editor-content"
        style={{
          width: '100%',
          height: '100%',
          backgroundColor: 'var(--semi-color-bg-1)',
          borderRadius: '8px',
          boxShadow: 'var(--semi-shadow-elevated)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden'
        }}
      >
        <div 
          className="custom-editor-header"
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '16px 24px',
            borderBottom: '1px solid var(--semi-color-border)'
          }}
        >
          <div className="custom-editor-title" style={{ 
            fontSize: '16px', 
            fontWeight: 600,
            color: 'var(--semi-color-text-0)'
          }}>
            Code Editor
          </div>
          <div className="custom-editor-close" onClick={handleCurrentCancel} style={{
            cursor: 'pointer',
            fontSize: '20px',
            lineHeight: 1,
            color: 'var(--semi-color-text-2)'
          }}>
            ×
          </div>
        </div>
        <div style={{ flex: 1, overflow: 'hidden', padding: '0 24px' }}>
          {editorContent}
        </div>
        <div 
          className="custom-editor-footer"
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            padding: '16px 24px',
            borderTop: '1px solid var(--semi-color-border)'
          }}
        >
          <button 
            onClick={handleCurrentCancel}
            style={{
              marginRight: '8px',
              padding: '6px 16px',
              border: '1px solid var(--semi-color-border)',
              borderRadius: '3px',
              backgroundColor: 'var(--semi-color-bg-2)',
              color: 'var(--semi-color-text-0)',
              cursor: 'pointer',
              fontSize: '14px',
              lineHeight: '20px'
            }}
          >
            Cancel
          </button>
          <button 
            onClick={handleCurrentOk}
            style={{
              padding: '6px 16px',
              border: 'none',
              borderRadius: '3px',
              backgroundColor: 'var(--semi-color-primary)',
              color: 'white',
              cursor: 'pointer',
              fontSize: '14px',
              lineHeight: '20px'
            }}
          >
            OK
          </button>
        </div>
      </div>
    </div>
  );
};
