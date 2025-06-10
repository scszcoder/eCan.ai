import React, { useCallback, useRef, useEffect, useMemo } from 'react';
import * as monaco from 'monaco-editor';

// Monaco Editor worker configuration
const MONACO_WORKER_CONFIG = {
  getWorkerUrl: function (_moduleId: string, label: string) {
    const workerMap: Record<string, string> = {
      typescript: './monaco-editor/esm/vs/language/typescript/ts.worker.js',
      javascript: './monaco-editor/esm/vs/language/typescript/ts.worker.js',
      json: './monaco-editor/esm/vs/language/json/json.worker.js',
      python: './monaco-editor/esm/vs/basic-languages/python/python.worker.js'
    };
    return workerMap[label] || './monaco-editor/esm/vs/editor/editor.worker.js';
  }
};

// Initialize Monaco environment
if (typeof self !== 'undefined') {
  self.MonacoEnvironment = MONACO_WORKER_CONFIG;
}

// Register supported languages
const SUPPORTED_LANGUAGES = ['python', 'javascript', 'typescript', 'json'];
SUPPORTED_LANGUAGES.forEach(lang => monaco.languages.register({ id: lang }));

// Common token patterns
const commonTokens: monaco.languages.IMonarchLanguageRule[] = [
  [/[{}]/, 'delimiter.bracket'],
  [/[\[\]]/, 'delimiter.array'],
  [/[()]/, 'delimiter.parenthesis'],
  [/[+\-*/%<>=!&|]/, 'operator'],
  [/[0-9]+/, 'number'],
  [/[a-zA-Z_]\w*/, 'identifier'],
  [/["].*?["]/, 'string'],
  [/['].*?[']/, 'string'],
  [/`.*?`/, 'string']
];

// Language configurations
const languageConfigs: Record<string, monaco.languages.IMonarchLanguage> = {
  python: {
    tokenizer: {
      root: [
        ...commonTokens,
        [/def\b|class\b|if\b|else\b|elif\b|while\b|for\b|in\b|try\b|except\b|finally\b|with\b|as\b|return\b|break\b|continue\b|pass\b|raise\b|import\b|from\b/, 'keyword'],
        [/True\b|False\b|None\b/, 'constant'],
        [/[#].*$/, 'comment'],
      ],
    },
  },
  javascript: {
    tokenizer: {
      root: [
        ...commonTokens,
        [/function\b|class\b|const\b|let\b|var\b|if\b|else\b|for\b|while\b|do\b|switch\b|case\b|break\b|continue\b|return\b|try\b|catch\b|finally\b|throw\b|new\b|this\b|super\b|import\b|export\b|default\b|async\b|await\b/, 'keyword'],
        [/true\b|false\b|null\b|undefined\b/, 'constant'],
        [/\/\/.*$/, 'comment'],
        [/\/\*/, 'comment', '@comment'],
      ],
      comment: [
        [/[^\/*]+/, 'comment'],
        [/\*\//, 'comment', '@pop'],
        [/[\/*]/, 'comment'],
      ],
    },
  },
  typescript: {
    tokenizer: {
      root: [
        ...commonTokens,
        [/function\b|class\b|const\b|let\b|var\b|if\b|else\b|for\b|while\b|do\b|switch\b|case\b|break\b|continue\b|return\b|try\b|catch\b|finally\b|throw\b|new\b|this\b|super\b|import\b|export\b|default\b|async\b|await\b|interface\b|type\b|enum\b|namespace\b|module\b|declare\b|public\b|private\b|protected\b|readonly\b|static\b/, 'keyword'],
        [/true\b|false\b|null\b|undefined\b/, 'constant'],
        [/\/\/.*$/, 'comment'],
        [/\/\*/, 'comment', '@comment'],
      ],
      comment: [
        [/[^\/*]+/, 'comment'],
        [/\*\//, 'comment', '@pop'],
        [/[\/*]/, 'comment'],
      ],
    },
  },
  json: {
    tokenizer: {
      root: [
        [/[{}]/, 'delimiter.bracket'],
        [/[\[\]]/, 'delimiter.array'],
        [/[,]/, 'delimiter'],
        [/[:]/, 'delimiter'],
        [/["].*?["]/, 'string'],
        [/[0-9]+/, 'number'],
        [/true|false|null/, 'constant'],
      ],
    },
  },
};

// Apply language configurations
Object.entries(languageConfigs).forEach(([language, config]) => {
  monaco.languages.setMonarchTokensProvider(language, config);
});

// Default editor options
const DEFAULT_EDITOR_OPTIONS: monaco.editor.IStandaloneEditorConstructionOptions = {
  fontSize: 14,
  lineNumbers: 'on',
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  automaticLayout: true,
  tabSize: 2,
  wordWrap: 'on',
  theme: 'vs-dark',
  renderWhitespace: 'selection',
  contextmenu: true,
  quickSuggestions: true,
  suggestOnTriggerCharacters: true,
  acceptSuggestionOnEnter: 'on',
  snippetSuggestions: 'inline',
  wordBasedSuggestions: 'currentDocument',
  parameterHints: { enabled: true },
  formatOnPaste: true,
  formatOnType: true,
  folding: true,
  foldingStrategy: 'indentation',
  showFoldingControls: 'always',
  matchBrackets: 'always',
  autoClosingBrackets: 'always',
  autoClosingQuotes: 'always',
  autoIndent: 'full',
  scrollbar: {
    vertical: 'visible',
    horizontal: 'visible',
    useShadows: true,
    verticalScrollbarSize: 10,
    horizontalScrollbarSize: 10,
  },
  gotoLocation: {
    multiple: 'goto',
    multipleDefinitions: 'goto',
    multipleTypeDefinitions: 'goto',
    multipleDeclarations: 'goto',
    multipleImplementations: 'goto',
    multipleReferences: 'goto',
    alternativeDefinitionCommand: 'editor.action.goToReferences',
    alternativeTypeDefinitionCommand: 'editor.action.goToReferences',
    alternativeDeclarationCommand: 'editor.action.goToReferences',
  },
  find: {
    addExtraSpaceOnTop: false,
    autoFindInSelection: 'never',
    seedSearchStringFromSelection: 'selection',
  },
};

interface CodeEditorProps {
  value: string;
  onChange?: (value: string) => void;
  language: string;
  visible: boolean;
  handleOk?: () => void;
  handleCancel?: () => void;
  onVisibleChange?: (visible: boolean) => void;
  options?: monaco.editor.IStandaloneEditorConstructionOptions;
  mode?: 'preview' | 'edit';
  height?: string | number;
  className?: string;
  style?: React.CSSProperties;
  onEditorDidMount?: (editor: monaco.editor.IStandaloneCodeEditor) => void;
}

export const CodeEditor: React.FC<CodeEditorProps> = ({
  value,
  onChange,
  language,
  visible,
  handleOk,
  handleCancel,
  onVisibleChange,
  options: externalOptions,
  mode = 'edit',
  height = 'calc(100vh - 120px)',
  className,
  style,
  onEditorDidMount,
}) => {
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const valueRef = useRef(value);

  const handleCurrentOk = useCallback(() => {
    handleOk?.();
    onVisibleChange?.(false);
  }, [handleOk, onVisibleChange]);

  const handleCurrentCancel = useCallback(() => {
    handleCancel?.();
    onVisibleChange?.(false);
  }, [handleCancel, onVisibleChange]);

  const editorOptions = useMemo(() => {
    const baseOptions = { ...DEFAULT_EDITOR_OPTIONS, ...externalOptions };
    
    if (mode === 'preview') {
      return {
        ...baseOptions,
        readOnly: true,
        lineNumbers: 'off' as const,
        folding: false,
        glyphMargin: false,
        lineDecorationsWidth: 0,
        lineNumbersMinChars: 0,
        renderLineHighlight: 'none' as const,
        overviewRulerBorder: false,
        hideCursorInOverviewRuler: true,
        overviewRulerLanes: 0,
        scrollbar: {
          vertical: 'hidden' as const,
          horizontal: 'hidden' as const
        }
      } as monaco.editor.IStandaloneEditorConstructionOptions;
    }
    
    return baseOptions;
  }, [mode, externalOptions]);

  useEffect(() => {
    if (visible && containerRef.current && !editorRef.current) {
      editorRef.current = monaco.editor.create(containerRef.current, {
        value,
        language,
        ...editorOptions,
      });

      onEditorDidMount?.(editorRef.current);

      const disposable = editorRef.current.onDidChangeModelContent(() => {
        const newValue = editorRef.current?.getValue();
        if (onChange && newValue !== undefined) {
          onChange(newValue);
        }
      });

      return () => {
        disposable.dispose();
        editorRef.current?.dispose();
        editorRef.current = null;
      };
    }
  }, [visible, language, editorOptions, onEditorDidMount]);

  useEffect(() => {
    if (editorRef.current && value !== valueRef.current) {
      valueRef.current = value;
      const currentValue = editorRef.current.getValue();
      if (value !== currentValue) {
        editorRef.current.setValue(value);
      }
    }
  }, [value]);

  // Add ESC key handler to match Modal's closeOnEsc behavior
  useEffect(() => {
    const handleEscKey = (event: KeyboardEvent) => {
      if (visible && event.key === 'Escape') {
        handleCurrentCancel();
      }
    };

    document.addEventListener('keydown', handleEscKey);
    return () => {
      document.removeEventListener('keydown', handleEscKey);
    };
  }, [visible, handleCurrentCancel]);

  const editorContent = (
    <div 
      ref={containerRef} 
      className={className}
      style={{ 
        height,
        width: '100%',
        border: '1px solid var(--semi-color-border)',
        borderRadius: '4px',
        overflow: 'hidden',
        ...style
      }}
    />
  );

  if (mode === 'preview') {
    return editorContent;
  }

  if (!visible) {
    return null;
  }

  return (
    <div 
      className="custom-editor-container"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 1000,
        backgroundColor: 'rgba(0, 0, 0, 0.6)', // Semi Modal overlay background
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        boxSizing: 'border-box'
      }}
    >
      <div 
        className="custom-editor-content"
        style={{
          width: '100%',
          height: '100%',
          backgroundColor: 'var(--semi-color-bg-1)',
          borderRadius: '8px',
          boxShadow: 'var(--semi-shadow-elevated)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden'
        }}
      >
        <div 
          className="custom-editor-header"
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '16px 24px',
            borderBottom: '1px solid var(--semi-color-border)'
          }}
        >
          <div className="custom-editor-title" style={{ 
            fontSize: '16px', 
            fontWeight: 600,
            color: 'var(--semi-color-text-0)'
          }}>
            Code Editor
          </div>
          <div className="custom-editor-close" onClick={handleCurrentCancel} style={{
            cursor: 'pointer',
            fontSize: '20px',
            lineHeight: 1,
            color: 'var(--semi-color-text-2)'
          }}>
            ×
          </div>
        </div>
        <div style={{ flex: 1, overflow: 'hidden', padding: '0 24px' }}>
          {editorContent}
        </div>
        <div 
          className="custom-editor-footer"
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            padding: '16px 24px',
            borderTop: '1px solid var(--semi-color-border)'
          }}
        >
          <button 
            onClick={handleCurrentCancel}
            style={{
              marginRight: '8px',
              padding: '6px 16px',
              border: '1px solid var(--semi-color-border)',
              borderRadius: '3px',
              backgroundColor: 'var(--semi-color-bg-2)',
              color: 'var(--semi-color-text-0)',
              cursor: 'pointer',
              fontSize: '14px',
              lineHeight: '20px'
            }}
          >
            Cancel
          </button>
          <button 
            onClick={handleCurrentOk}
            style={{
              padding: '6px 16px',
              border: 'none',
              borderRadius: '3px',
              backgroundColor: 'var(--semi-color-primary)',
              color: 'white',
              cursor: 'pointer',
              fontSize: '14px',
              lineHeight: '20px'
            }}
          >
            OK
          </button>
        </div>
      </div>
    </div>
  );
};
