import type { editor } from 'monaco-editor';
import type { EditorProps as MonacoEditorProps } from '@monaco-editor/react';

export type SupportedLanguage = 'javascript' | 'typescript' | 'html' | 'css' | 'json' | 'markdown' | 'plaintext' | 'python';

export interface CodeEditorProps extends Omit<MonacoEditorProps, 'onChange'> {
  value: string;
  onChange?: (value: string) => void;
  language?: SupportedLanguage;
  options?: Record<string, any>;
}

export interface CodeEditorComponentProps extends CodeEditorProps {
  visible?: boolean;
  handleOk?: () => void;
  handleCancel?: () => void;
  onVisibleChange?: (visible: boolean) => void;
  mode?: 'edit' | 'preview';
  height?: string;
  className?: string;
  style?: React.CSSProperties;
  onEditorDidMount?: (editor: editor.IStandaloneCodeEditor) => void;
}

export interface UseCodeEditorProps extends Omit<CodeEditorComponentProps, 'value' | 'onChange'> {
  initialContent: string;
  onSave?: (content: string) => boolean;
}

export interface UseCodeEditorReturn {
  openEditor: (content: string) => void;
  closeEditor: () => void;
  editor: JSX.Element;
} 