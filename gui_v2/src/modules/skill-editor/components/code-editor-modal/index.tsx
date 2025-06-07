import React, { useCallback, useRef, useEffect } from 'react';
import { Modal } from '@douyinfe/semi-ui';
import * as monaco from 'monaco-editor';

// 配置 monaco-editor 的 worker 路径
self.MonacoEnvironment = {
  getWorkerUrl: function (_moduleId: string, label: string) {
    if (label === 'typescript' || label === 'javascript') {
      return './monaco-editor/esm/vs/language/typescript/ts.worker.js';
    }
    if (label === 'json') {
      return './monaco-editor/esm/vs/language/json/json.worker.js';
    }
    if (label === 'css') {
      return './monaco-editor/esm/vs/language/css/css.worker.js';
    }
    if (label === 'html') {
      return './monaco-editor/esm/vs/language/html/html.worker.js';
    }
    if (label === 'python') {
      return './monaco-editor/esm/vs/basic-languages/python/python.worker.js';
    }
    return './monaco-editor/esm/vs/editor/editor.worker.js';
  }
};

// 注册语言
monaco.languages.register({ id: 'python' });
monaco.languages.register({ id: 'javascript' });
monaco.languages.register({ id: 'typescript' });
monaco.languages.register({ id: 'html' });
monaco.languages.register({ id: 'css' });
monaco.languages.register({ id: 'json' });

// 配置语言特性
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

// 应用语言配置
Object.entries(languageConfigs).forEach(([language, config]) => {
  monaco.languages.setMonarchTokensProvider(language, config);
});

interface CodeEditorModalProps {
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

export const CodeEditorModal: React.FC<CodeEditorModalProps> = ({
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

  // 默认配置
  const defaultOptions: monaco.editor.IStandaloneEditorConstructionOptions = {
    fontSize: 14,
    lineNumbers: 'on' as const,
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    automaticLayout: true,
    tabSize: 4,
    wordWrap: 'on',
    theme: 'vs-dark',
    ...(language === 'python' ? {
      insertSpaces: true,
      detectIndentation: true,
      trimTrailingWhitespace: true,
      insertFinalNewline: true,
    } : {}),
  };

  const mergedOptions = { 
    ...defaultOptions, 
    ...externalOptions,
    ...(mode === 'preview' ? {
      readOnly: true,
      lineNumbers: 'off' as const,
      folding: false,
      glyphMargin: false,
      lineDecorationsWidth: 0,
      lineNumbersMinChars: 0,
      renderLineHighlight: 'none',
      overviewRulerBorder: false,
      hideCursorInOverviewRuler: true,
      overviewRulerLanes: 0,
      scrollbar: {
        vertical: 'hidden' as const,
        horizontal: 'hidden' as const
      }
    } : {})
  };

  useEffect(() => {
    if (visible && containerRef.current && !editorRef.current) {
      editorRef.current = monaco.editor.create(containerRef.current, {
        value,
        language,
        ...mergedOptions,
      });

      editorRef.current.onDidChangeModelContent(() => {
        const newValue = editorRef.current?.getValue();
        if (onChange && newValue !== undefined) {
          onChange(newValue);
        }
      });
    }

    return () => {
      editorRef.current?.dispose();
      editorRef.current = null;
    };
  }, [visible, language]);

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
        border: '1px solid #ccc',
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
