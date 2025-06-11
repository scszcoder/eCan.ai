import type { IStandaloneEditorConstructionOptions } from '@/modules/monaco-editor';

export const DEFAULT_EDITOR_HEIGHT = 'calc(100vh - 120px)';

export const getPreviewModeOptions = (baseOptions: IStandaloneEditorConstructionOptions): IStandaloneEditorConstructionOptions => ({
  ...baseOptions,
  readOnly: true,
  lineNumbers: 'off',
  folding: false,
  glyphMargin: false,
  lineDecorationsWidth: 0,
  lineNumbersMinChars: 0,
  renderLineHighlight: 'none',
  overviewRulerBorder: false,
  hideCursorInOverviewRuler: true,
  overviewRulerLanes: 0,
  scrollbar: {
    vertical: 'hidden',
    horizontal: 'hidden'
  }
}); 