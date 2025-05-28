import { useState, useCallback } from 'react';

import { CodeEditorModal } from '../components/code-editor-modal';

export const useModal = (initialContent: string, language: string, onOk?: (content: string) => boolean) => {
  const [content, setContent] = useState(initialContent);
  const [isVisible, setIsVisible] = useState(false);

  const openModal = (newContent: string) => {
    setContent(newContent);
    setIsVisible(true);
  };

  const closeModal = () => {
    setIsVisible(false);
  };

  const handleChange = useCallback((newContent: string) => {
    setContent(newContent);
  }, []);

  const handleOk = useCallback(() => {
    if (onOk) {
      return onOk(content);
    }
    return true;
  }, [content, onOk]);

  const modal = (
    <CodeEditorModal
      value={content}
      language={language}
      visible={isVisible}
      onVisibleChange={setIsVisible}
      onChange={handleChange}
      handleOk={handleOk}
      options={{ readOnly: false }}
    />
  );

  return { openModal, closeModal, modal };
};
