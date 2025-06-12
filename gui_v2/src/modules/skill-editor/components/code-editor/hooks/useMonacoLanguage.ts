import { useCallback } from 'react';
import { setMonacoLanguage } from '../CodeEditor';

type Language = 'en' | 'zh-cn';

export const useMonacoLanguage = () => {
  const changeLanguage = useCallback((language: Language) => {
    setMonacoLanguage(language);
    // 重新加载编辑器以应用新的语言设置
    window.location.reload();
  }, []);

  return {
    changeLanguage,
    // 预定义的可用语言
    availableLanguages: ['en', 'zh-cn'] as const,
  };
}; 