import type { editor } from 'monaco-editor';

export const DEFAULT_EDITOR_HEIGHT = '400px';

export const DEFAULT_EDITOR_OPTIONS: editor.IStandaloneEditorConstructionOptions = {
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  fontSize: 14,
  lineNumbers: 'on',
  readOnly: false,
  automaticLayout: true,
  tabSize: 2,
  wordWrap: 'on',
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

export const getPreviewModeOptions = (baseOptions: editor.IStandaloneEditorConstructionOptions): editor.IStandaloneEditorConstructionOptions => ({
  ...baseOptions,
  readOnly: true,
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  lineNumbers: 'off',
  folding: false,
  contextmenu: false,
}); 