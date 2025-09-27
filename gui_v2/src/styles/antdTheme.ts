import { ThemeConfig } from 'antd';

/**
 * Ant Design 主题配置
 * 包含 zIndex 层级管理，避免 zIndex 警告
 */
export const antdTheme: ThemeConfig = {
  token: {
    // 基础 zIndex 配置，避免过高的 zIndex 值
    zIndexBase: 1000,
    zIndexPopupBase: 1000,
    
    // 其他主题配置
    colorPrimary: '#1890ff',
    borderRadius: 6,
    
    // 字体配置
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  },
  
  components: {
    // 只配置确实存在的属性
    Modal: {
      // Modal 相关配置
    },
    
    Drawer: {
      // Drawer 相关配置
    },
    
    Menu: {
      // Menu 相关配置
    },
    
    Tooltip: {
      // Tooltip 相关配置
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
