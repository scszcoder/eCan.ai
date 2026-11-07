import { ThemeConfig, theme } from 'antd';

/**
 * Single source of truth for Ant Design's theme.
 *
 * These values MUST mirror the CSS custom properties in styles/global.css
 * (`:root` = dark, `body.light` = light). Both surfaces describe the same
 * design system from two directions — TS for antd components, CSS for our own
 * styles — so when a token changes, change it in BOTH files.
 *
 * Brand palette (kept from the original design):
 *   primary #3b82f6 · success #22c55e · warning #fbbf24 · error #ef4444 · info #06b6d4
 */

/** Dark palette — mirrors global.css `:root`. */
const darkPalette = {
    colorPrimary: '#3b82f6',
    /* Link TEXT must clear AA on --bg-secondary #1e293b; the base brand blue
       lands on 3.98:1. Use the dark text ramp (matches --primary-text). */
    colorLink: '#6ea8fe',
    colorLinkHover: '#93c5fd',
    colorLinkActive: '#93c5fd',
    colorSuccess: '#22c55e',
    colorWarning: '#fbbf24',
    colorError: '#ef4444',
    colorInfo: '#06b6d4',

    bgLayout: '#0f172a',
    bgContainer: '#1e293b',
    bgElevated: '#1e293b',
    bgSunken: '#0b1120',

    border: 'rgba(255, 255, 255, 0.08)',
    borderSecondary: 'rgba(255, 255, 255, 0.06)',

    text: '#f8fafc',
    textSecondary: '#94a3b8',
    textTertiary: '#94a3b8',
    textQuaternary: '#8290a5',
} as const;

/** Light palette — mirrors global.css `body.light`. */
const lightPalette = {
    colorPrimary: '#2563eb',
    colorPrimaryHover: '#1d4ed8',
    /* Light theme: the brand blue already clears AA as text (5.17:1 on white). */
    colorLink: '#2563eb',
    colorLinkHover: '#1d4ed8',
    colorLinkActive: '#1d4ed8',
    colorSuccess: '#166534',
    colorWarning: '#92400e',
    colorError: '#b91c1c',
    colorInfo: '#0e7490',

    /* Mirror of the light surface ramp in global.css `body.light`.
       MUST stay byte-equal to `--bg-primary` there: antd paints this on
       `.ant-layout` with higher precedence than a plain background token, so a
       drift here silently reverts the whole page to another tone. The canvas is
       #e8ecf3 so that a white card separates at 1.185:1 (a #f4f6fa page only
       reached 1.077:1 and every plane collapsed into one white sheet). */
    bgLayout: '#e8ecf3',
    bgContainer: '#fff',
    bgElevated: '#fff',
    bgSunken: '#f2f5fa',

    /* Matches --border-color; on the deeper canvas 16% is the first alpha
       where a 1px card edge reads without turning into a drawn outline. */
    border: 'rgba(15, 23, 42, 0.16)',
    borderSecondary: 'rgba(15, 23, 42, 0.10)',

    text: '#0f172a',
    textSecondary: '#475569',
    textTertiary: '#5f6c80',
    textQuaternary: '#5b6b7f',
} as const;

/**
 * Build the Ant Design ThemeConfig for a given mode.
 * Replaces the previous inline definition in App.tsx (which had drifted from
 * this file — e.g. warning #eab308 vs #fbbf24, radius 8 vs 10).
 */
export const getAntdThemeConfig = (isDark: boolean = true): ThemeConfig => {
    const p = isDark ? darkPalette : lightPalette;

    return {
        token: {
            // Base zIndex 层级管理，避免过高的 zIndex 值
            zIndexBase: 1000,
            zIndexPopupBase: 1000,

            // Brand
            colorPrimary: p.colorPrimary,
            colorSuccess: p.colorSuccess,
            colorWarning: p.colorWarning,
            colorError: p.colorError,
            colorInfo: p.colorInfo,
            // antd derives link/typography-link colour from colorInfo by default,
            // which made every .ant-btn-link render off-brand cyan. Pin it to the
            // per-theme link ramp (dark uses the AA-safe text blue).
            colorLink: p.colorLink,
            colorLinkHover: p.colorLinkHover,
            colorLinkActive: p.colorLinkActive,
            wireframe: false,

            // Surfaces
            colorBgLayout: p.bgLayout,
            colorBgContainer: p.bgContainer,
            colorBgElevated: p.bgElevated,

            // Borders & text
            colorBorder: p.border,
            colorBorderSecondary: p.borderSecondary,
            colorText: p.text,
            colorTextSecondary: p.textSecondary,
            colorTextTertiary: p.textTertiary,
            colorTextQuaternary: p.textQuaternary,
            // antd derives card/statistic/empty description color from these.
            // NOTE: components with a *visible* name/description (and the
            // TextArea placeholder) rendered through `--text-tertiary`, which is
            // 4.75:1 on raised dark cards. `textQuaternary` is now only used for
            // true placeholder-level hints, so it can stay the dimmest step.
            colorTextDescription: p.textTertiary,
            colorTextHeading: p.text,
            colorTextLabel: p.textSecondary,
            colorTextPlaceholder: p.textQuaternary,

            // Radius — mirrors --radius-* in global.css
            borderRadius: 8,
            borderRadiusLG: 12,
            borderRadiusSM: 6,

            // Typography
            // MUST mirror --font-family in global.css, otherwise antd controls
            // render in a different typeface from the body copy beside them.
            // CJK families are named explicitly so glyphs do not fall back
            // per-element (which read as inconsistently light CJK text).
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", sans-serif, "Apple Color Emoji", "Segoe UI Emoji"',
            fontSize: 14,
            fontSizeHeading1: 32,
            fontSizeHeading2: 24,
            fontSizeHeading3: 20,
            fontSizeHeading4: 16,
            fontSizeHeading5: 14,

            // Shadows
            boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)',
            boxShadowSecondary: '0 4px 16px rgba(0, 0, 0, 0.2)',

            // Motion
            motionDurationSlow: '0.3s',
            motionDurationMid: '0.2s',
            motionDurationFast: '0.1s',

            // Spacing
            padding: 16,
            paddingLG: 24,
            paddingSM: 12,
            paddingXS: 8,
            margin: 16,
            marginLG: 24,
            marginSM: 12,
            marginXS: 8,
        },

        algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,

        components: {
            Layout: {
                bodyBg: p.bgLayout,
                headerBg: p.bgContainer,
                siderBg: p.bgContainer,
            },

            Menu: {
                itemBorderRadius: 8,
                itemHeight: 44,
                itemMarginBlock: 6,
                itemMarginInline: 12,
                darkItemBg: p.bgContainer,
                darkItemSelectedBg: isDark ? '#334155' : 'rgba(37, 99, 235, 0.12)',
                darkItemHoverBg: isDark ? '#334155' : 'rgba(15, 23, 42, 0.05)',
            },

            Card: {
                borderRadiusLG: 12,
                colorBgContainer: p.bgContainer,
                colorBorderSecondary: p.borderSecondary,
            },

            Button: {
                borderRadiusLG: 8,
                controlHeight: 40,
                controlHeightLG: 48,
                controlHeightSM: 32,
                fontWeight: 600,
                colorPrimary: p.colorPrimary,
                colorPrimaryHover: p.colorPrimaryHover,
            },

            Input: {
                borderRadiusLG: 8,
                controlHeight: 40,
                paddingBlock: 0,
                paddingInline: 12,
                lineHeight: 1.5,
                colorBgContainer: isDark ? '#334155' : '#fff',
                colorBorder: isDark ? '#475569' : 'var(--border-color)',
            },

            Table: {
                borderRadiusLG: 12,
                colorBgContainer: p.bgContainer,
                /* Was #fafafa (1.021:1 on white) — a table header the user could not see. */
                headerBg: isDark ? p.bgContainer : '#f4f7fb',
                headerColor: p.text,
                rowHoverBg: isDark ? '#334155' : '#fafafa',
            },

            Modal: {
                borderRadiusLG: 16,
                paddingContentHorizontalLG: 24,
            },

            Drawer: {
                paddingLG: 24,
            },

            Tooltip: {
                borderRadius: 8,
            },
        },
    };
};

/**
 * 各组件的推荐 zIndex 值。
 */
export const getComponentZIndex = {
    tooltip: 1050,
    dropdown: 1050,
    popover: 1050,
    modal: 2000,
    drawer: 2000,
    message: 3000,
    notification: 3000,
    // 自定义组件
    userDropdown: 3000, // 用户下拉菜单需要在最上层
    dragPreview: 1500,
    resizeHandle: 1500,
    resizeCorner: 1501,
} as const;
