import React, { createContext, useContext, useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';

interface LanguageContextType {
    currentLanguage: string;
    changeLanguage: (language: string) => void;
}

const LanguageContext = createContext<LanguageContextType>({
    currentLanguage: 'zh-CN',
    changeLanguage: () => {},
});

export const useLanguage = () => useContext(LanguageContext);

export const LanguageProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const { i18n } = useTranslation();
    const [currentLanguage, setCurrentLanguage] = useState(i18n.language || 'zh-CN');

    useEffect(() => {
        // Initialize时从 localStorage Get语言Settings
        const savedLanguage = localStorage.getItem('i18nextLng');
        if (savedLanguage) {
            setCurrentLanguage(savedLanguage);
            i18n.changeLanguage(savedLanguage);
        }
    }, [i18n]);

    const changeLanguage = (language: string) => {
        setCurrentLanguage(language);
        i18n.changeLanguage(language);
        localStorage.setItem('i18nextLng', language);
        document.documentElement.lang = language;
    };

    return (
        <LanguageContext.Provider value={{ currentLanguage, changeLanguage }}>
            {children}
        </LanguageContext.Provider>
    );
}; 