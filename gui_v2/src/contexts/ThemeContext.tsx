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


/**
 * Resolve a theme preference to a concrete 'light' | 'dark'.
 * 'system' follows the OS setting. Exported so shell components (AppSider,
 * AppHeader) agree with App.tsx instead of re-deriving the rule differently.
 */
export const resolveTheme = (theme: Theme): 'light' | 'dark' => {
    if (theme === 'system') {
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    return theme;
};

export const useTheme = () => useContext(ThemeContext);

/** The resolved theme ('light' | 'dark') for the current preference. */
export const useResolvedTheme = (): 'light' | 'dark' => resolveTheme(useTheme().theme);

/**
 * Apply a resolved theme to the document.
 *
 * The ONLY thing this function does is set `light` / `dark` on <body>: every
 * colour is already declared in styles/global.css (`:root` = dark defaults,
 * `body.light` = light overrides). Writing individual custom properties here
 * used to shadow those declarations with a second, divergent palette —
 * don't reintroduce that. Add or change tokens in global.css instead.
 */
const applyResolvedTheme = (resolved: 'light' | 'dark') => {
    document.body.className = resolved;
    document.documentElement.setAttribute('data-theme', resolved);
};

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [theme, setTheme] = useState<Theme>(() => {
        const savedTheme = localStorage.getItem('theme') as Theme;
        const initialTheme = savedTheme || 'dark';

        // 立即应用主题，避免白色闪烁
        applyResolvedTheme(resolveTheme(initialTheme));

        return initialTheme;
    });

    useEffect(() => {
        // Save主题Settings到 localStorage
        localStorage.setItem('theme', theme);

        applyResolvedTheme(resolveTheme(theme));
    }, [theme]);

    // ListenSystem主题变化
    useEffect(() => {
        if (theme === 'system') {
            const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
            const handleChange = () => applyResolvedTheme(resolveTheme('system'));

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
