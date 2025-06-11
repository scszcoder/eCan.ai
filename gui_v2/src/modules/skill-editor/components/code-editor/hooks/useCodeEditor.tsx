import { useState, useCallback, useRef } from 'react';
import type { editor } from 'monaco-editor';
import { CodeEditor } from '..';
import type { UseCodeEditorProps, UseCodeEditorReturn } from '../types';
import { DEFAULT_EDITOR_OPTIONS } from '../config';

/**
 * Hook for managing a code editor modal
 * 
 * Features:
 * - Modal-based code editor
 * - Content management
 * - Editor state management
 * - Save/Cancel operations
 * 
 * @param props - Editor configuration options
 * @returns Editor management functions and editor component
 */
export const useCodeEditor = ({
  initialContent = '',
  language,
  onSave,
  mode = 'edit',
  height,
  className,
  style,
  visible = false,
  options: externalOptions,
  onEditorDidMount,
}: UseCodeEditorProps): UseCodeEditorReturn => {
  // State
  const [isVisible, setIsVisible] = useState(visible);
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const contentRef = useRef(initialContent);

  // Editor operations
  const openEditor = useCallback((newContent: string) => {
    contentRef.current = newContent;
    if (editorRef.current) {
      editorRef.current.setValue(newContent);
    }
    setIsVisible(true);
  }, []);

  const closeEditor = useCallback(() => {
    setIsVisible(false);
  }, []);

  const handleChange = useCallback((newContent: string) => {
    contentRef.current = newContent;
  }, []);

  const handleSave = useCallback(() => {
    if (onSave) {
      return onSave(contentRef.current);
    }
    return true;
  }, [onSave]);

  // Editor lifecycle
  const handleEditorDidMount = useCallback((editor: editor.IStandaloneCodeEditor) => {
    editorRef.current = editor;
    editor.setValue(contentRef.current);
    editor.layout();
    onEditorDidMount?.(editor);
  }, [onEditorDidMount]);

  // Editor configuration
  const editorOptions = useCallback(() => ({
    ...DEFAULT_EDITOR_OPTIONS,
    ...externalOptions,
  }), [externalOptions]);

  // Render editor component
  const editor = (
    <CodeEditor
      value={contentRef.current}
      language={language}
      visible={isVisible}
      onVisibleChange={setIsVisible}
      onChange={handleChange}
      handleOk={handleSave}
      options={editorOptions()}
      onEditorDidMount={handleEditorDidMount}
      mode={mode}
      height={height}
      className={className}
      style={style}
    />
  );

  return { openEditor, closeEditor, editor };
}; 