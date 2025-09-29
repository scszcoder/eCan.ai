import { useEffect, useCallback } from 'react';
import { eventBus } from '@/utils/eventBus';
import { logger } from '@/utils/logger';

/**
 * 自定义 Hook：监听组织数据更新事件
 * 无论在哪个页面都执行回调函数，更新数据
 */
export const useOrgAgentsUpdate = (
  callback: () => void,
  dependencies: any[] = [],
  componentName?: string
) => {
  // 使用 useCallback 确保回调函数的稳定性
  const stableCallback = useCallback(callback, dependencies);

  useEffect(() => {
    const handleOrgAgentsUpdate = (data: any) => {
      const caller = componentName || 'Unknown';
      logger.info(`[useOrgAgentsUpdate:${caller}] Received org-agents-update event:`, data);
      logger.info(`[useOrgAgentsUpdate:${caller}] Executing callback to update data...`);
      
      // 直接执行回调，不检查页面
      stableCallback();
    };

    // 注册事件监听器
    eventBus.on('org-agents-update', handleOrgAgentsUpdate);

    // 清理函数：组件卸载时移除监听器
    return () => {
      eventBus.off('org-agents-update', handleOrgAgentsUpdate);
    };
  }, [stableCallback, componentName]);
};
