import { useState, useCallback, useRef } from 'react';

import { CodeEditor } from '../components/code-editor';

interface UseCodeEditorProps {
  initialContent: string;
  language: string;
  onSave?: (content: string) => boolean;
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
 */
export const useCodeEditor = ({
  initialContent,
  language,
  onSave,
}: UseCodeEditorProps): UseCodeEditorReturn => {
  const [isVisible, setIsVisible] = useState(false);
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
  }, []);

  const editor = (
    <CodeEditor
      value={contentRef.current}
      language={language}
      visible={isVisible}
      onVisibleChange={setIsVisible}
      onChange={handleChange}
      handleOk={handleSave}
      options={{ readOnly: false }}
      onEditorDidMount={handleEditorDidMount}
    />
  );

  return { openEditor, closeEditor, editor };
};
