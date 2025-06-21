import { useState, useCallback, useEffect, useRef } from 'react';
import { message } from 'antd';
import { IPCAPI } from '@/services/ipc/api';
import { useUserStore } from '../../../stores/userStore';
import { useDetailView } from '../../../hooks/useDetailView';
import { Knowledge } from '../types';
import { useTranslation } from 'react-i18next';

export function useKnowledgeData() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState<Record<string, any>>({});
  const username = useUserStore((state) => state.username);

  const {
    selectedItem: selectedKnowledge,
    items: knowledges,
    selectItem,
    updateItem,
    updateItems: setKnowledges
  } = useDetailView<Knowledge>([]);

  // 使用ref来存储setKnowledges函数，避免依赖问题
  const setKnowledgesRef = useRef(setKnowledges);
  setKnowledgesRef.current = setKnowledges;

  // 数据获取
  const fetchKnowledgePoints = useCallback(async () => {
    try {
      setLoading(true);
      const username = localStorage.getItem('username') || '';
      const response = await IPCAPI.getInstance().getKnowledges(username, []);
      if (response && response.success && response.data) {
        setKnowledgesRef.current(response.data as Knowledge[]);
      }
    } catch (error) {
      console.error('Error fetching knowledge points:', error);
      message.error(t('pages.knowledge.fetchError'));
    } finally {
      setLoading(false);
    }
  }, [t]); // 移除setKnowledges依赖

  // 只在组件挂载时执行一次，避免重复执行
  useEffect(() => { 
    fetchKnowledgePoints(); 
  }, []); // 移除fetchKnowledgePoints依赖

  // 事件处理
  const handleRefresh = useCallback(async () => {
    await fetchKnowledgePoints();
    message.success(t('pages.knowledge.refreshSuccess'));
  }, [fetchKnowledgePoints, t]);

  const handleStatusChange = (id: number, newStatus: 'active' | 'maintenance' | 'offline') => {
    updateItem(id, {
      status: newStatus,
      location: newStatus === 'maintenance' ? t('pages.knowledge.maintenanceBay') :
        newStatus === 'offline' ? t('pages.knowledge.chargingStation') : t('pages.knowledge.zoneA'),
    });
  };

  const handleTaskComplete = (id: number) => {
    const knowledgePoint = knowledges.find(k => k.id === id);
    if (knowledgePoint) {
      updateItem(id, {
        status: 'active',
        currentTask: undefined,
        totalDistance: knowledgePoint.totalDistance + 10,
        battery: Math.max(knowledgePoint.battery - 5, 0),
      });
    }
  };

  const handleMaintenance = (id: number) => {
    const knowledgePoint = knowledges.find(k => k.id === id);
    if (knowledgePoint) {
      updateItem(id, {
        status: 'maintenance',
        location: t('pages.knowledge.maintenanceBay'),
        lastMaintenance: t('pages.knowledge.lastMaintenance', { time: t('pages.schedule.justNow') }),
        nextMaintenance: t('pages.knowledge.nextMaintenance', { time: t('pages.schedule.twoWeeksFromNow') }),
      });
    }
  };

  const handleSearch = (value: string) => { /* 可扩展 */ };
  const handleFilterChange = (newFilters: Record<string, any>) => setFilters(prev => ({ ...prev, ...newFilters }));
  const handleReset = () => setFilters({});

  return {
    loading, filters, selectedKnowledge, knowledges, selectItem, updateItem, setKnowledges,
    handleRefresh, handleStatusChange, handleTaskComplete, handleMaintenance,
    handleSearch, handleFilterChange, handleReset
  };
} 