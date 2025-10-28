/**
 * Z-Index 层级管理
 * 
 * Ant Design 推荐的 zIndex Range：
 * - Base层：1-99
 * - 弹出层：1000-1999 (Tooltip, Dropdown, Popover)
 * - 模态层：2000-2999 (Modal, Drawer)
 * - Notification层：3000-3999 (Message, Notification)
 * - 最高层：4000+ (极特殊情况)
 */

export const zIndexLevels = {
  // Base层级 (1-99)
  base: 1,
  nodeIndicator: 10,
  breadcrumb: 10,
  
  // Content层级 (100-999)
  nodeInfo: 100,
  nodeConnection: 110,
  door: 2,
  
  // 弹出层级 (1000-1999) - 与 Ant Design Compatible
  popup: 1000,
  tooltip: 1000,
  dropdown: 1000,
  sidebar: 1000,
  collaboration: 1000,
  nodeInfoDisplay: 1000,
  codeEditorOverlay: 1000,
  
  // Drag和交互层级 (1500-1999)
  dragPreview: 1500,
  resizeHandle: 1500,
  resizeCorner: 1501,
  
  // 模态层级 (2000-2999)
  modal: 2000,
  drawer: 2000,
  
  // 最高Priority (3000+)
  notification: 3000,
  userDropdown: 3000, // User下拉MenuNeed在最上层
} as const;

export type ZIndexLevel = keyof typeof zIndexLevels;

/**
 * Get指定层级的 zIndex Value
 */
export function getZIndex(level: ZIndexLevel): number {
  return zIndexLevels[level];
}

/**
 * Get相对于指定层级的 zIndex Value
 */
export function getRelativeZIndex(level: ZIndexLevel, offset: number = 0): number {
  return zIndexLevels[level] + offset;
}
