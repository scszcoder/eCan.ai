import * as monaco from 'monaco-editor';

// TypeScript/JavaScript 配置
export const configureTypeScript = () => {
  // 确保 typescript 语言特性已经加载
  if (!monaco.languages.typescript) {
    console.warn('TypeScript language features not loaded yet');
    return;
  }

  monaco.languages.typescript.typescriptDefaults.setCompilerOptions({
    target: monaco.languages.typescript.ScriptTarget.ES2020,
    allowNonTsExtensions: true,
    moduleResolution: monaco.languages.typescript.ModuleResolutionKind.NodeJs,
    module: monaco.languages.typescript.ModuleKind.CommonJS,
    noEmit: true,
    esModuleInterop: true,
    jsx: monaco.languages.typescript.JsxEmit.React,
    reactNamespace: 'React',
    allowJs: true,
    typeRoots: ['node_modules/@types']
  });
};

// Python 配置
export const configurePython = () => {
  // 注册代码补全提供程序
  monaco.languages.registerCompletionItemProvider('python', {
    provideCompletionItems: (model, position) => {
      const word = model.getWordUntilPosition(position);
      const range = {
        startLineNumber: position.lineNumber,
        endLineNumber: position.lineNumber,
        startColumn: word.startColumn,
        endColumn: word.endColumn
      };

      const suggestions = [
        {
          label: 'def',
          kind: monaco.languages.CompletionItemKind.Keyword,
          insertText: 'def ${1:function_name}(${2:parameters}):\n\t${0}',
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          range
        },
        {
          label: 'class',
          kind: monaco.languages.CompletionItemKind.Keyword,
          insertText: 'class ${1:class_name}:\n\tdef __init__(self):\n\t\t${0}',
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          range
        },
        {
          label: 'if',
          kind: monaco.languages.CompletionItemKind.Keyword,
          insertText: 'if ${1:condition}:\n\t${0}',
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          range
        },
        {
          label: 'for',
          kind: monaco.languages.CompletionItemKind.Keyword,
          insertText: 'for ${1:item} in ${2:items}:\n\t${0}',
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          range
        },
        {
          label: 'while',
          kind: monaco.languages.CompletionItemKind.Keyword,
          insertText: 'while ${1:condition}:\n\t${0}',
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          range
        },
        {
          label: 'try',
          kind: monaco.languages.CompletionItemKind.Keyword,
          insertText: 'try:\n\t${1}\nexcept ${2:Exception} as ${3:e}:\n\t${0}',
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          range
        },
        {
          label: 'with',
          kind: monaco.languages.CompletionItemKind.Keyword,
          insertText: 'with ${1:expression} as ${2:target}:\n\t${0}',
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          range
        }
      ];
      return { suggestions };
    }
  });

  // 注册格式化提供程序
  monaco.languages.registerDocumentFormattingEditProvider('python', {
    provideDocumentFormattingEdits: async (model) => {
      // TODO: 实现 Python 代码格式化
      return [];
    }
  });
};

// 注册所有语言特性
export const configureLanguages = () => {
  // 等待 Monaco Editor 完全加载
  const waitForMonaco = () => {
    if (monaco.languages.typescript) {
      configureTypeScript();
      configurePython();
    } else {
      setTimeout(waitForMonaco, 100);
    }
  };

  waitForMonaco();
}; 