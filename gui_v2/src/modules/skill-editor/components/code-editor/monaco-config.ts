import { loader } from '@monaco-editor/react';

// Configure Monaco Editor to use local files
// This MUST run before any Monaco Editor component mounts
loader.config({
  paths: {
    vs: '/monaco-editor/vs'
  }
});

// Configure Monaco worker paths
if (typeof window !== 'undefined') {
  (window as any).MonacoEnvironment = {
    getWorkerUrl: function (_moduleId: string, _label: string) {
      return '/monaco-editor/vs/base/worker/workerMain.js';
    }
  };
}

export const setMonacoLanguage = (language: 'en' | 'zh-cn') => {
  loader.config({
    'vs/nls': {
      availableLanguages: {
        '*': language
      }
    }
  });
};
