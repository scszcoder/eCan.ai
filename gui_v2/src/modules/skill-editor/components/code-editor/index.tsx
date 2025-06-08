import React, { useCallback, useRef, useEffect, useMemo } from 'react';
import { Modal } from '@douyinfe/semi-ui';
import * as monaco from 'monaco-editor';

// Monaco Editor worker configuration
const MONACO_WORKER_CONFIG = {
  getWorkerUrl: function (_moduleId: string, label: string) {
    const workerMap: Record<string, string> = {
      typescript: './monaco-editor/esm/vs/language/typescript/ts.worker.js',
      javascript: './monaco-editor/esm/vs/language/typescript/ts.worker.js',
      json: './monaco-editor/esm/vs/language/json/json.worker.js',
      css: './monaco-editor/esm/vs/language/css/css.worker.js',
      html: './monaco-editor/esm/vs/language/html/html.worker.js',
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
const SUPPORTED_LANGUAGES = ['python', 'javascript', 'typescript', 'html', 'css', 'json'];
SUPPORTED_LANGUAGES.forEach(lang => monaco.languages.register({ id: lang }));

// Language configurations
const languageConfigs: Record<string, monaco.languages.IMonarchLanguage> = {
  python: {
    tokenizer: {
      root: [
        [/[{}]/, 'delimiter.bracket'],
        [/[\[\]]/, 'delimiter.array'],
        [/[()]/, 'delimiter.parenthesis'],
        [/[;]/, 'delimiter'],
        [/[=]/, 'delimiter'],
        [/[+\-*/%]/, 'operator'],
        [/[<>=!&|]/, 'operator'],
        [/def\b/, 'keyword'],
        [/class\b/, 'keyword'],
        [/if\b|else\b|elif\b|while\b|for\b|in\b|try\b|except\b|finally\b|with\b|as\b|return\b|break\b|continue\b|pass\b|raise\b|import\b|from\b/, 'keyword'],
        [/True\b|False\b|None\b/, 'constant'],
        [/[0-9]+/, 'number'],
        [/[a-zA-Z_]\w*/, 'identifier'],
        [/["].*?["]/, 'string'],
        [/['].*?[']/, 'string'],
        [/""".*?"""/, 'string'],
        [/'''.*?'''/, 'string'],
        [/[#].*$/, 'comment'],
      ],
    },
  },
  javascript: {
    tokenizer: {
      root: [
        [/[{}]/, 'delimiter.bracket'],
        [/[\[\]]/, 'delimiter.array'],
        [/[()]/, 'delimiter.parenthesis'],
        [/[;]/, 'delimiter'],
        [/[=]/, 'delimiter'],
        [/[+\-*/%]/, 'operator'],
        [/[<>=!&|]/, 'operator'],
        [/function\b|class\b|const\b|let\b|var\b|if\b|else\b|for\b|while\b|do\b|switch\b|case\b|break\b|continue\b|return\b|try\b|catch\b|finally\b|throw\b|new\b|this\b|super\b|import\b|export\b|default\b|async\b|await\b/, 'keyword'],
        [/true\b|false\b|null\b|undefined\b/, 'constant'],
        [/[0-9]+/, 'number'],
        [/[a-zA-Z_]\w*/, 'identifier'],
        [/["].*?["]/, 'string'],
        [/['].*?[']/, 'string'],
        [/`.*?`/, 'string'],
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
        [/[{}]/, 'delimiter.bracket'],
        [/[\[\]]/, 'delimiter.array'],
        [/[()]/, 'delimiter.parenthesis'],
        [/[;]/, 'delimiter'],
        [/[=]/, 'delimiter'],
        [/[+\-*/%]/, 'operator'],
        [/[<>=!&|]/, 'operator'],
        [/function\b|class\b|const\b|let\b|var\b|if\b|else\b|for\b|while\b|do\b|switch\b|case\b|break\b|continue\b|return\b|try\b|catch\b|finally\b|throw\b|new\b|this\b|super\b|import\b|export\b|default\b|async\b|await\b|interface\b|type\b|enum\b|namespace\b|module\b|declare\b|public\b|private\b|protected\b|readonly\b|static\b/, 'keyword'],
        [/true\b|false\b|null\b|undefined\b/, 'constant'],
        [/[0-9]+/, 'number'],
        [/[a-zA-Z_]\w*/, 'identifier'],
        [/["].*?["]/, 'string'],
        [/['].*?[']/, 'string'],
        [/`.*?`/, 'string'],
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
  html: {
    tokenizer: {
      root: [
        [/<!DOCTYPE/, 'metatag', '@doctype'],
        [/<!--/, 'comment', '@comment'],
        [/(<)(\w+)(\/>)/, ['delimiter', 'tag', 'delimiter']],
        [/(<)(script)/, ['delimiter', { token: 'tag', next: '@script' }]],
        [/(<)(style)/, ['delimiter', { token: 'tag', next: '@style' }]],
        [/(<)(\w+)/, ['delimiter', { token: 'tag', next: '@tag' }]],
        [/[ \t\r\n]+/, 'white'],
        [/[^<]+/, 'text'],
      ],
      doctype: [
        [/[^>]+/, 'metatag.content'],
        [/>/, 'metatag', '@pop'],
      ],
      comment: [
        [/-->/, 'comment', '@pop'],
        [/[^-]+/, 'comment.content'],
        [/./, 'comment.content'],
      ],
      tag: [
        [/[ \t\r\n]+/, 'white'],
        [/(\/)(>)/, ['delimiter', 'delimiter']],
        [/>/, 'delimiter', '@pop'],
        [/[^>]+/, 'attribute.name'],
      ],
      script: [
        [/<\/(script)>/, ['delimiter', 'tag', 'delimiter']],
        [/[^<]+/, 'javascript'],
      ],
      style: [
        [/<\/(style)>/, ['delimiter', 'tag', 'delimiter']],
        [/[^<]+/, 'css'],
      ],
    },
  },
  css: {
    tokenizer: {
      root: [
        [/[{}]/, 'delimiter.bracket'],
        [/[\[\]]/, 'delimiter.array'],
        [/[()]/, 'delimiter.parenthesis'],
        [/[;]/, 'delimiter'],
        [/[=]/, 'delimiter'],
        [/[+\-*/%]/, 'operator'],
        [/[<>=!&|]/, 'operator'],
        [/[a-zA-Z-]+(?=\s*:)/, 'attribute.name'],
        [/:[^;]+/, 'attribute.value'],
        [/[0-9]+/, 'number'],
        [/#[0-9a-fA-F]+/, 'number.hex'],
        [/[a-zA-Z_]\w*/, 'identifier'],
        [/["].*?["]/, 'string'],
        [/['].*?[']/, 'string'],
        [/\/\*/, 'comment', '@comment'],
        [/\/\/.*$/, 'comment'],
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
  tabSize: 4,
  wordWrap: 'on',
  theme: 'vs-dark',
  renderWhitespace: 'selection',
  contextmenu: true,
  quickSuggestions: true,
  suggestOnTriggerCharacters: true,
  acceptSuggestionOnEnter: 'on',
  snippetSuggestions: 'inline',
  wordBasedSuggestions: 'currentDocument',
  parameterHints: {
    enabled: true
  }
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
}) => {
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleCurrentOk = useCallback(() => {
    handleOk?.();
    onVisibleChange?.(false);
  }, [handleOk, onVisibleChange]);

  const handleCurrentCancel = useCallback(() => {
    handleCancel?.();
    onVisibleChange?.(false);
  }, [handleCancel, onVisibleChange]);

  // Memoize editor options
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

  // Initialize editor
  useEffect(() => {
    if (visible && containerRef.current && !editorRef.current) {
      editorRef.current = monaco.editor.create(containerRef.current, {
        value,
        language,
        ...editorOptions,
      });

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
  }, [visible, language, editorOptions]);

  // Update editor value
  useEffect(() => {
    if (editorRef.current && value !== editorRef.current.getValue()) {
      editorRef.current.setValue(value);
    }
  }, [value]);

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
      {editorContent}
    </Modal>
  );
};
