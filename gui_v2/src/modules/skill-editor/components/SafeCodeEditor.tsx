import React, { useCallback, useRef, useEffect } from 'react';
import Editor, { OnChange } from '@monaco-editor/react';
import type { editor } from 'monaco-editor';

interface SafeCodeEditorProps {
  languageId?: string;
  value: string;
  onChange?: (value: string) => void;
  readonly?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Adapter around Monaco Editor to replace the CodeMirror-based
 * CodeEditor from @flowgram.ai/form-materials in sensitive places.
 * Keeps a compatible surface: languageId, value, onChange, readonly.
 * Renders inline without modal, with full control over readonly state.
 */
export const SafeCodeEditor: React.FC<SafeCodeEditorProps> = ({
  languageId = 'plaintext',
  value,
  onChange,
  readonly,
  className,
  style,
}) => {
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);

  const handleChange: OnChange = useCallback((value) => {
    onChange?.(value || '');
  }, [onChange]);

  const handleEditorDidMount = useCallback((editor: editor.IStandaloneCodeEditor) => {
    editorRef.current = editor;
    editor.setValue(value);
    editor.layout();
  }, [value]);

  useEffect(() => {
    if (editorRef.current && editorRef.current.getValue() !== value) {
      editorRef.current.setValue(value);
      editorRef.current.layout();
    }
  }, [value]);

  const editorOptions: editor.IStandaloneEditorConstructionOptions = {
    readOnly: readonly || false,
    minimap: { enabled: false },
    automaticLayout: true,
    fontSize: 14,
    lineNumbers: 'on',
    tabSize: 2,
    wordWrap: 'on',
    scrollBeyondLastLine: false,
    folding: true,
    lineDecorationsWidth: 0,
    lineNumbersMinChars: 3,
    glyphMargin: false,
    contextmenu: true,
    scrollbar: {
      vertical: 'visible',
      horizontal: 'visible',
      useShadows: false,
      verticalScrollbarSize: 6,
      horizontalScrollbarSize: 6,
    },
  };

  return (
    <div
      className={className}
      style={{
        height: '260px',
        width: '100%',
        border: '1px solid var(--semi-color-border)',
        borderRadius: '4px',
        overflow: 'hidden',
        ...style
      }}
    >
      <Editor
        value={value}
        language={languageId}
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
};
