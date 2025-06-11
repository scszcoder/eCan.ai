import type { IStandaloneCodeEditor, CodeEditorProps } from '@/modules/monaco-editor';

export interface CodeEditorComponentProps extends CodeEditorProps {
  visible?: boolean;
  handleOk?: () => void;
  handleCancel?: () => void;
  onVisibleChange?: (visible: boolean) => void;
  mode?: 'edit' | 'preview';
  height?: string;
  className?: string;
  style?: React.CSSProperties;
  onEditorDidMount?: (editor: IStandaloneCodeEditor) => void;
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