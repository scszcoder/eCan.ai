import React from 'react';
import { CodeEditor as MonacoCodeEditor } from './code-editor/CodeEditor';

interface SafeCodeEditorProps {
  languageId?: string;
  value: string;
  onChange?: (value: string) => void;
  readonly?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Adapter around our Monaco-based CodeEditor to replace the CodeMirror-based
 * CodeEditor from @flowgram.ai/form-materials in sensitive places.
 * Keeps a compatible surface: languageId, value, onChange, readonly.
 */
export const SafeCodeEditor: React.FC<SafeCodeEditorProps> = ({
  languageId = 'plaintext',
  value,
  onChange,
  readonly,
  className,
  style,
}) => {
  // Monaco's CodeEditor signature: value, onChange, language, options
  const language = languageId as any;
  const options = {
    ...(readonly ? { readOnly: true } : {}),
    minimap: { enabled: false },
    automaticLayout: true,
  } as any;
  return (
    <MonacoCodeEditor
      value={value}
      onChange={onChange}
      language={language}
      options={options}
      className={className}
      style={style}
      // Use default edit mode and a stable height to avoid layout thrash
      height="260px"
      mode="preview"
    />
  );
};
