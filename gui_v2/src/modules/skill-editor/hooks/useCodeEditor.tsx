import { useState, useCallback } from 'react';

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
  const [content, setContent] = useState(initialContent);
  const [isVisible, setIsVisible] = useState(false);

  const openEditor = useCallback((newContent: string) => {
    setContent(newContent);
    setIsVisible(true);
  }, []);

  const closeEditor = useCallback(() => {
    setIsVisible(false);
  }, []);

  const handleChange = useCallback((newContent: string) => {
    setContent(newContent);
  }, []);

  const handleSave = useCallback(() => {
    if (onSave) {
      return onSave(content);
    }
    return true;
  }, [content, onSave]);

  const editor = (
    <CodeEditor
      value={content}
      language={language}
      visible={isVisible}
      onVisibleChange={setIsVisible}
      onChange={handleChange}
      handleOk={handleSave}
      options={{ readOnly: false }}
    />
  );

  return { openEditor, closeEditor, editor };
};
