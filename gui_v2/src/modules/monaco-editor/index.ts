export * from './components/MonacoEditor';
export * from './config/editor.config';
export * from './config/language-features';

// Define our own types
export interface IStandaloneEditorConstructionOptions {
  value?: string;
  language?: string;
  theme?: string;
  automaticLayout?: boolean;
  minimap?: { enabled: boolean };
  scrollBeyondLastLine?: boolean;
  readOnly?: boolean;
  lineNumbers?: 'on' | 'off';
  folding?: boolean;
  glyphMargin?: boolean;
  lineDecorationsWidth?: number;
  lineNumbersMinChars?: number;
  renderLineHighlight?: 'all' | 'line' | 'none';
  overviewRulerBorder?: boolean;
  hideCursorInOverviewRuler?: boolean;
  overviewRulerLanes?: number;
  scrollbar?: {
    vertical?: 'auto' | 'visible' | 'hidden';
    horizontal?: 'auto' | 'visible' | 'hidden';
  };
  [key: string]: any;
}

export interface IStandaloneCodeEditor {
  getValue(): string;
  setValue(value: string): void;
  getModel(): any;
  layout(): void;
  dispose(): void;
  onDidChangeModelContent(listener: () => void): { dispose(): void };
  [key: string]: any;
}

export interface CodeEditorProps {
  value: string;
  onChange?: (value: string) => void;
  language: string;
  visible: boolean;
  handleOk?: () => void;
  handleCancel?: () => void;
  onVisibleChange?: (visible: boolean) => void;
  options?: IStandaloneEditorConstructionOptions;
  mode?: 'preview' | 'edit';
  height?: string | number;
  className?: string;
  style?: React.CSSProperties;
  onEditorDidMount?: (editor: IStandaloneCodeEditor) => void;
} 