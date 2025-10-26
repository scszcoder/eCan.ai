import { ThemeConfig } from 'antd';

/**
 * Ant Design 主题配置
 * 包含 zIndex 层级管理和完整的设计系统配置
 */
export const antdTheme: ThemeConfig = {
  token: {
    // 基础 zIndex 配置，避免过高的 zIndex 值
    zIndexBase: 1000,
    zIndexPopupBase: 1000,
    
    // 主色调 - 蓝紫渐变
    colorPrimary: '#3b82f6',
    colorSuccess: '#22c55e',
    colorWarning: '#fbbf24',
    colorError: '#ef4444',
    colorInfo: '#06b6d4',
    
    // 圆角配置
    borderRadius: 10,
    borderRadiusLG: 16,
    borderRadiusSM: 8,
    
    // 字体配置
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif, "Apple Color Emoji", "Segoe UI Emoji"',
    fontSize: 14,
    fontSizeHeading1: 32,
    fontSizeHeading2: 24,
    fontSizeHeading3: 20,
    fontSizeHeading4: 16,
    fontSizeHeading5: 14,
    
    // 阴影配置
    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)',
    boxShadowSecondary: '0 4px 16px rgba(0, 0, 0, 0.2)',
    
    // 动画配置
    motionDurationSlow: '0.3s',
    motionDurationMid: '0.2s',
    motionDurationFast: '0.1s',
    
    // 间距配置
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
 * 获取组件的推荐 zIndex 值
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
