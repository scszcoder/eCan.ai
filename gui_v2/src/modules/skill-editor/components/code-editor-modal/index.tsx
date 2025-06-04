import React, { useCallback } from 'react';
import { Modal } from '@douyinfe/semi-ui';
import Editor from '@monaco-editor/react';

interface CodeEditorModalProps {
  value: string;
  onChange?: (value: string) => void;
  language: string;
  visible: boolean;
  handleOk?: () => void;
  handleCancel?: () => void;
  onVisibleChange?: (visible: boolean) => void;
  options?: any; // Monaco Editor options
}

export const CodeEditorModal: React.FC<CodeEditorModalProps> = ({
  value,
  onChange,
  language,
  visible,
  handleOk,
  handleCancel,
  onVisibleChange,
  options: externalOptions,
}) => {
  const handleCurrentOk = useCallback(() => {
    if (handleOk) {
      handleOk();
    }
    if (onVisibleChange) {
      onVisibleChange(false);
    }
  }, [handleOk, onVisibleChange]);

  const handleCurrentCancel = useCallback(() => {
    if (handleCancel) {
      handleCancel();
    }
    if (onVisibleChange) {
      onVisibleChange(false);
    }
  }, [handleCancel, onVisibleChange]);

  // 默认配置
  const defaultOptions = {
    fontSize: 14,
    lineNumbers: 'on',
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    automaticLayout: true,
    tabSize: 2,
    wordWrap: 'on',
  };

  const mergedOptions = { ...defaultOptions, ...externalOptions };

  const handleEditorChange = (value: string | undefined) => {
    if (onChange && value !== undefined) {
      onChange(value);
    }
  };

  return (
    <Modal
      title="Code Editor"
      visible={visible}
      onOk={handleCurrentOk}
      onCancel={handleCurrentCancel}
      closeOnEsc
      fullScreen
      style={{ zIndex: 1000 }}
      getPopupContainer={() => document.body}
    >
      <Editor
        height="calc(100vh - 120px)"
        defaultLanguage={language}
        language={language}
        value={value}
        onChange={handleEditorChange}
        theme="vs-dark"
        options={mergedOptions}
        loading={<div>Loading editor...</div>}
      />
    </Modal>
  );
};
