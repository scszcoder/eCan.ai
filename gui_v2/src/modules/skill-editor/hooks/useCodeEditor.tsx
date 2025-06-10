import { useState, useCallback, useRef } from 'react';
import * as monaco from 'monaco-editor';

import { CodeEditor } from '../components/code-editor';

interface UseCodeEditorProps {
  initialContent: string;
  language: string;
  onSave?: (content: string) => boolean;
  mode?: 'preview' | 'edit';
  height?: string | number;
  className?: string;
  style?: React.CSSProperties;
  visible?: boolean;
  options?: monaco.editor.IStandaloneEditorConstructionOptions;
  onEditorDidMount?: (editor: monaco.editor.IStandaloneCodeEditor) => void;
}

interface UseCodeEditorReturn {
  openEditor: (content: string) => void;
  closeEditor: () => void;
  editor: JSX.Element;
}

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
  initialContent,
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
  const editorRef = useRef<any>(null);
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

  const handleEditorDidMount = useCallback((editor: any) => {
    editorRef.current = editor;
    editor.setValue(contentRef.current);
    if (onEditorDidMount) {
      onEditorDidMount(editor);
    }
  }, [onEditorDidMount]);

  const editor = (
    <CodeEditor
      value={contentRef.current}
      language={language}
      visible={isVisible}
      onVisibleChange={setIsVisible}
      onChange={handleChange}
      handleOk={handleSave}
      options={externalOptions}
      onEditorDidMount={handleEditorDidMount}
      mode={mode}
      height={height}
      className={className}
      style={style}
    />
  );

  return { openEditor, closeEditor, editor };
};
