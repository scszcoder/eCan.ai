import { editor } from 'monaco-editor';

declare global {
  interface Window {
    monaco?: {
      editor: typeof editor;
    };
  }
}

// 亮色主题配置
export const lightTheme: editor.IStandaloneThemeData = {
  base: 'vs',
  inherit: true,
  rules: [
    { token: 'comment', foreground: '6A9955' },
    { token: 'keyword', foreground: 'C586C0' },
    { token: 'string', foreground: 'CE9178' },
    { token: 'number', foreground: 'B5CEA8' },
    { token: 'type', foreground: '4EC9B0' },
    { token: 'function', foreground: 'DCDCAA' },
    { token: 'variable', foreground: '9CDCFE' },
    { token: 'operator', foreground: 'D4D4D4' },
  ],
  colors: {
    'editor.background': '#FFFFFF',
    'editor.foreground': '#000000',
    'editor.lineHighlightBackground': '#F0F0F0',
    'editor.selectionBackground': '#ADD6FF',
    'editor.inactiveSelectionBackground': '#E5EBF1',
    'editorLineNumber.foreground': '#858585',
    'editorError.foreground': '#E51400',
    'editorWarning.foreground': '#BF8803',
  }
};

// 暗色主题配置
export const darkTheme: editor.IStandaloneThemeData = {
  base: 'vs-dark',
  inherit: true,
  rules: [
    { token: 'comment', foreground: '6A9955' },
    { token: 'keyword', foreground: 'C586C0' },
    { token: 'string', foreground: 'CE9178' },
    { token: 'number', foreground: 'B5CEA8' },
    { token: 'type', foreground: '4EC9B0' },
    { token: 'function', foreground: 'DCDCAA' },
    { token: 'variable', foreground: '9CDCFE' },
    { token: 'operator', foreground: 'D4D4D4' },
  ],
  colors: {
    'editor.background': '#1E1E1E',
    'editor.foreground': '#D4D4D4',
    'editor.lineHighlightBackground': '#2A2D2E',
    'editor.selectionBackground': '#264F78',
    'editor.inactiveSelectionBackground': '#3A3D41',
    'editorLineNumber.foreground': '#858585',
    'editorError.foreground': '#F48771',
    'editorWarning.foreground': '#CCA700',
  }
};

// 注册主题
export const registerThemes = () => {
  if (window.monaco?.editor) {
    window.monaco.editor.defineTheme('light', lightTheme);
    window.monaco.editor.defineTheme('dark', darkTheme);
    // 设置默认主题为 dark
    window.monaco.editor.setTheme('dark');
  }
};

// 获取当前主题
export const getCurrentTheme = () => {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  return isDark ? 'dark' : 'light';
}; 