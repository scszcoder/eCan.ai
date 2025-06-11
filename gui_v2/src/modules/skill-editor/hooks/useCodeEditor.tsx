import { useState, useCallback, useRef } from 'react';
import type { editor } from 'monaco-editor';
import { CodeEditor } from '../components/code-editor';
import type { UseCodeEditorProps, UseCodeEditorReturn } from '../components/code-editor/types';
import { DEFAULT_EDITOR_OPTIONS } from '../components/code-editor/config';

/**
 * Hook for managing a code editor modal
 * @param initialContent - Initial content of the editor
 * @param language - Programming language for syntax highlighting
 * @param onSave - Optional callback when saving the content
 * @param mode - Editor mode: 'preview' for read-only preview, 'edit' for editable content
 * @param height - Height of the editor
 * @param className - Additional CSS class name
 * @param style - Additional CSS styles
 * @param visible - Whether the editor is visible
 * @param options - Additional Monaco editor options
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
  const [isVisible, setIsVisible] = useState(visible);
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const contentRef = useRef(initialContent);

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

  const handleEditorDidMount = useCallback((editor: editor.IStandaloneCodeEditor) => {
    editorRef.current = editor;
    editor.setValue(contentRef.current);
    editor.layout();
    onEditorDidMount?.(editor);
  }, [onEditorDidMount]);

  const editorOptions = useCallback(() => ({
    ...DEFAULT_EDITOR_OPTIONS,
    ...externalOptions,
  }), [externalOptions]);

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
