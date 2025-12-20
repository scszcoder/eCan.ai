import { ThemeConfig } from 'antd';

/**
 * Ant Design 主题Configuration
 * Include zIndex 层级管理和完整的设计SystemConfiguration
 */
export const antdTheme: ThemeConfig = {
  token: {
    // Base zIndex Configuration，避免过高的 zIndex Value
    zIndexBase: 1000,
    zIndexPopupBase: 1000,
    
    // 主色调 - 蓝紫渐变
    colorPrimary: '#3b82f6',
    colorSuccess: '#22c55e',
    colorWarning: '#fbbf24',
    colorError: '#ef4444',
    colorInfo: '#06b6d4',
    
    // 圆角Configuration
    borderRadius: 10,
    borderRadiusLG: 16,
    borderRadiusSM: 8,
    
    // 字体Configuration
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif, "Apple Color Emoji", "Segoe UI Emoji"',
    fontSize: 14,
    fontSizeHeading1: 32,
    fontSizeHeading2: 24,
    fontSizeHeading3: 20,
    fontSizeHeading4: 16,
    fontSizeHeading5: 14,
    
    // 阴影Configuration
    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)',
    boxShadowSecondary: '0 4px 16px rgba(0, 0, 0, 0.2)',
    
    // 动画Configuration
    motionDurationSlow: '0.3s',
    motionDurationMid: '0.2s',
    motionDurationFast: '0.1s',
    
    // 间距Configuration
    padding: 16,
    paddingLG: 24,
    paddingSM: 12,
    paddingXS: 8,
    margin: 16,
    marginLG: 24,
    marginSM: 12,
    marginXS: 8,
  },
  
  components: {
    Modal: {
      borderRadiusLG: 20,
      paddingContentHorizontalLG: 24,
    },
    
    Drawer: {
      paddingLG: 24,
    },
    
    Menu: {
      itemBorderRadius: 10,
      itemHeight: 44,
      itemMarginBlock: 6,
      itemMarginInline: 12,
    },
    
    Button: {
      borderRadiusLG: 10,
      controlHeight: 40,
      controlHeightLG: 48,
      controlHeightSM: 32,
      fontWeight: 600,
    },
    
    Input: {
      borderRadiusLG: 10,
      controlHeight: 40,
      paddingBlock: 0,
      paddingInline: 12,
      lineHeight: 1.5,
    },
    
    Card: {
      borderRadiusLG: 16,
      paddingLG: 24,
      headerHeight: 48,
    },
    
    Table: {
      borderRadiusLG: 16,
      padding: 16,
    },
    
    Tooltip: {
      borderRadius: 8,
    },
  },
};

/**
 * GetComponent的推荐 zIndex Value
 */
export const getComponentZIndex = {
  tooltip: 1050,
  dropdown: 1050,
  popover: 1050,
  modal: 2000,
  drawer: 2000,
  message: 3000,
  notification: 3000,
  // CustomComponent
  userDropdown: 3000, // User下拉MenuNeed在最上层
  dragPreview: 1500,
  resizeHandle: 1500,
  resizeCorner: 1501,
} as const;
