import type { editor } from 'monaco-editor';

export const DEFAULT_EDITOR_HEIGHT = '400px';

// BaseEdit器Configuration
export const DEFAULT_EDITOR_OPTIONS: editor.IStandaloneEditorConstructionOptions = {
  theme: 'vs-dark',
  fontSize: 14,
  lineNumbers: 'on',
  readOnly: false,
  automaticLayout: true,
  tabSize: 2,
  wordWrap: 'on',
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  folding: true,
  lineDecorationsWidth: 0,
  lineNumbersMinChars: 3,
  glyphMargin: false,
  contextmenu: true,
  scrollbar: {
    vertical: 'visible',
    horizontal: 'visible',
    useShadows: false,
    verticalScrollbarSize: 6,
    horizontalScrollbarSize: 6,
  },
};

// 预览模式Configuration
export const getPreviewModeOptions = (baseOptions: editor.IStandaloneEditorConstructionOptions): editor.IStandaloneEditorConstructionOptions => ({
  ...baseOptions,
  readOnly: true,
  lineNumbers: 'off',
  folding: false,
  contextmenu: false,
}); 