/**
 * Store Sync Service
 * 
 * 监听后端通知并同步更新前端 store
 * 确保数据在所有页面保持一致
 */

import { eventBus } from './eventBus';
import { useOrgStore } from '../stores/orgStore';
import { useAgentStore } from '../stores/agentStore';
import { logger } from '../utils/logger';

/**
 * 初始化 store 同步监听器
 */
export function initializeStoreSync() {
  // 监听组织-代理更新事件
  eventBus.on('org-agents-update', handleOrgAgentsUpdate);
  
  logger.info('[StoreSync] Store synchronization listeners initialized');
}

/**
 * 清理 store 同步监听器
 */
export function cleanupStoreSync() {
  eventBus.off('org-agents-update', handleOrgAgentsUpdate);
  
  logger.info('[StoreSync] Store synchronization listeners cleaned up');
}

/**
 * 处理组织-代理更新事件
 */
function handleOrgAgentsUpdate(event: any) {
  try {
    logger.info('[StoreSync] Received org-agents-update event:', event);
    
    const { data } = event;
    if (!data) {
      logger.warn('[StoreSync] No data in org-agents-update event');
      return;
    }
    
    // 获取 store 实例
    const orgStore = useOrgStore.getState();
    const agentStore = useAgentStore.getState();
    
    // 根据事件类型更新 store
    const { action, org_id, agent_id, agent_data, org_data } = data;
    
    switch (action) {
      case 'bind_agent':
        // 绑定代理到组织
        if (org_id && agent_id && agent_data) {
          logger.info(`[StoreSync] Binding agent ${agent_id} to org ${org_id}`);
          
          // 更新 org store
          orgStore.addAgentToOrg(org_id, {
            id: agent_id,
            name: agent_data.name || '',
            org_id: org_id,
            ...agent_data
          });
          
          // 更新 agent store
          agentStore.updateAgentOrganization(agent_id, org_id);
        }
        break;
        
      case 'unbind_agent':
        // 解绑代理
        if (agent_id) {
          logger.info(`[StoreSync] Unbinding agent ${agent_id}`);
          
          // 更新 org store
          orgStore.removeAgentFromOrg(agent_id);
          
          // 更新 agent store
          agentStore.updateAgentOrganization(agent_id, null);
        }
        break;
        
      case 'update_org':
        // 更新组织信息
        if (org_id && org_data) {
          logger.info(`[StoreSync] Updating org ${org_id}`);
          
          // 更新 org store
          orgStore.updateOrg(org_id, org_data);
        }
        break;
        
      case 'update_agent':
        // 更新代理信息
        if (agent_id && agent_data) {
          logger.info(`[StoreSync] Updating agent ${agent_id}`);
          
          // 更新 org store 中的 agent
          orgStore.updateAgent(agent_id, agent_data);
          
          // 更新 agent store
          agentStore.updateAgent(agent_id, agent_data);
        }
        break;
        
      default:
        logger.warn(`[StoreSync] Unknown action: ${action}`);
    }
  } catch (error) {
    logger.error('[StoreSync] Error handling org-agents-update:', error);
  }
}

/**
 * 手动触发 store 同步（用于测试或特殊情况）
 */
export function triggerStoreSync(action: string, data: any) {
  eventBus.emit('org-agents-update', {
    timestamp: Date.now(),
    source: 'manual_trigger',
    data: {
      action,
      ...data
    }
  });
}
