import * as monaco from 'monaco-editor';

// Monaco Editor worker configuration
export const MONACO_WORKER_CONFIG = {
  getWorkerUrl: function (_moduleId: string, label: string) {
    const basePath = process.env.NODE_ENV === 'production' ? './monaco-editor' : '/monaco-editor';
    if (label === 'typescript' || label === 'javascript') {
      return `${basePath}/vs/language/typescript/ts.worker.js`;
    }
    if (label === 'json') {
      return `${basePath}/vs/language/json/json.worker.js`;
    }
    if (label === 'python') {
      return `${basePath}/vs/basic-languages/python/python.worker.js`;
    }
    return `${basePath}/vs/editor/editor.worker.js`;
  }
};

// 默认编辑器配置
export const DEFAULT_EDITOR_OPTIONS: monaco.editor.IStandaloneEditorConstructionOptions = {
  theme: 'vs-dark',
  automaticLayout: true,
  minimap: {
    enabled: true,
  },
  scrollBeyondLastLine: false,
  fontSize: 14,
  lineNumbers: 'on',
  roundedSelection: false,
  scrollbar: {
    vertical: 'visible',
    horizontal: 'visible',
    useShadows: false,
    verticalScrollbarSize: 10,
    horizontalScrollbarSize: 10,
  },
  tabSize: 2,
  wordWrap: 'on',
  folding: true,
  lineDecorationsWidth: 0,
  lineNumbersMinChars: 3,
  glyphMargin: false,
  contextmenu: true,
  quickSuggestions: true,
  suggestOnTriggerCharacters: true,
  acceptSuggestionOnEnter: 'on',
  snippetSuggestions: 'inline',
  wordBasedSuggestions: true,
  parameterHints: {
    enabled: true,
  },
  bracketPairColorization: {
    enabled: true,
  },
  guides: {
    bracketPairs: true,
    indentation: true,
  },
  formatOnPaste: true,
  formatOnType: true,
};

// 支持的语言列表
export const SUPPORTED_LANGUAGES = ['python', 'javascript', 'typescript', 'json'] as const;
export type SupportedLanguage = typeof SUPPORTED_LANGUAGES[number]; 