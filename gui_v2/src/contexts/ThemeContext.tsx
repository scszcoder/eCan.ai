import React, { createContext, useContext, useState, useEffect } from 'react';

type Theme = 'light' | 'dark' | 'system';

interface ThemeContextType {
    theme: Theme;
    changeTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextType>({
    theme: 'dark',
    changeTheme: () => {},
});

export const useTheme = () => useContext(ThemeContext);

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [theme, setTheme] = useState<Theme>(() => {
        const savedTheme = localStorage.getItem('theme') as Theme;
        const initialTheme = savedTheme || 'dark';

        // 立即应用主题，避免白色闪烁
        const applyInitialTheme = (themeToApply: 'light' | 'dark') => {
            document.body.className = themeToApply;
            if (themeToApply === 'dark') {
                document.documentElement.style.setProperty('--bg-color', '#141414');
                document.documentElement.style.setProperty('--text-color', 'rgba(255, 255, 255, 0.85)');
                document.documentElement.style.setProperty('--card-bg', '#1f1f1f');
                document.documentElement.style.setProperty('--border-color', '#303030');
            } else {
                document.documentElement.style.setProperty('--bg-color', '#f0f2f5');
                document.documentElement.style.setProperty('--text-color', 'rgba(0, 0, 0, 0.85)');
                document.documentElement.style.setProperty('--card-bg', '#ffffff');
                document.documentElement.style.setProperty('--border-color', '#f0f0f0');
            }
        };

        if (initialTheme === 'system') {
            const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
            applyInitialTheme(systemTheme);
        } else {
            applyInitialTheme(initialTheme);
        }

        return initialTheme;
    });

    const applyTheme = (themeToApply: 'light' | 'dark') => {
        document.body.className = themeToApply;
        // Settings CSS 变量
        if (themeToApply === 'dark') {
            document.documentElement.style.setProperty('--bg-color', '#141414');
            document.documentElement.style.setProperty('--text-color', 'rgba(255, 255, 255, 0.85)');
            document.documentElement.style.setProperty('--card-bg', '#1f1f1f');
            document.documentElement.style.setProperty('--border-color', '#303030');
        } else {
            document.documentElement.style.setProperty('--bg-color', '#f0f2f5');
            document.documentElement.style.setProperty('--text-color', 'rgba(0, 0, 0, 0.85)');
            document.documentElement.style.setProperty('--card-bg', '#ffffff');
            document.documentElement.style.setProperty('--border-color', '#f0f0f0');
        }
    };

    useEffect(() => {
        // Save主题Settings到 localStorage
        localStorage.setItem('theme', theme);

        // 根据主题Settings样式
        if (theme === 'system') {
            const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
            applyTheme(systemTheme);
        } else {
            applyTheme(theme);
        }
    }, [theme]);

    // ListenSystem主题变化
    useEffect(() => {
        if (theme === 'system') {
            const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
            const handleChange = (e: MediaQueryListEvent) => {
                applyTheme(e.matches ? 'dark' : 'light');
            };

            mediaQuery.addEventListener('change', handleChange);
            return () => mediaQuery.removeEventListener('change', handleChange);
        }
    }, [theme]);

    const changeTheme = (newTheme: Theme) => {
        setTheme(newTheme);
    };

    return (
        <ThemeContext.Provider value={{ theme, changeTheme }}>
            {children}
        </ThemeContext.Provider>
    );
}; 