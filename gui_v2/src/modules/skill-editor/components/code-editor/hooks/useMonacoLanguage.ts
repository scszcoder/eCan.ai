import { useCallback } from 'react';
import { setMonacoLanguage } from '../CodeEditor';

type Language = 'en' | 'zh-cn';

export const useMonacoLanguage = () => {
  const changeLanguage = useCallback((language: Language) => {
    setMonacoLanguage(language);
    // 重新LoadEdit器以应用新的语言Settings
    window.location.reload();
  }, []);

  return {
    changeLanguage,
    // 预Definition的Available语言
    availableLanguages: ['en', 'zh-cn'] as const,
  };
}; 