import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import zhCN from 'antd/locale/zh_CN';
import enUS from 'antd/locale/en_US';

// Import翻译文件
import enTranslations from './locales/en-US.json';
import zhTranslations from './locales/zh-CN.json';

// GetSave的语言Settings或Browser语言
const getInitialLanguage = () => {
    const savedLanguage = localStorage.getItem('i18nextLng');
    if (savedLanguage) {
        return savedLanguage;
    }
    const browserLanguage = navigator.language;
    return ['en-US', 'zh-CN'].includes(browserLanguage) ? browserLanguage : 'zh-CN';
};

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      'en-US': {
        translation: enTranslations,
      },
      'zh-CN': {
        translation: zhTranslations,
      },
    },
    lng: getInitialLanguage(),
    fallbackLng: 'zh-CN',
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: 'i18nextLng'
    },
    react: {
      useSuspense: false,
      bindI18n: 'languageChanged loaded',
      bindI18nStore: 'added removed',
      transEmptyNodeValue: '',
      transSupportBasicHtmlNodes: true,
      transKeepBasicHtmlNodesFor: ['br', 'strong', 'i', 'p'],
    }
  });

// Listen语言变化
i18n.on('languageChanged', (lng) => {
  localStorage.setItem('i18nextLng', lng);
  document.documentElement.lang = lng;
});

// Export i18n 实例和 antd 语言Configuration
export const getAntdLocale = () => {
  const currentLang = i18n.language;
  return currentLang === 'zh-CN' ? zhCN : enUS;
};

export default i18n; 