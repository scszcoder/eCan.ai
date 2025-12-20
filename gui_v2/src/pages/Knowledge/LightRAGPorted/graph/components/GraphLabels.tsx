import React, { useCallback, useEffect, useState } from 'react';
import { Button, theme, Tooltip } from 'antd';
import { RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useSettingsStore } from '../stores/settings';
import { useGraphStore } from '../stores/graph';
import { SearchHistoryManager } from '../utils/SearchHistoryManager';
import { getPopularLabels, searchLabels } from '../api/lightrag';
import AsyncSelect from './AsyncSelect';

const DROPDOWN_DISPLAY_LIMIT = 15;
const POPULAR_LABELS_DEFAULT_LIMIT = 10;
const SEARCH_LABELS_DEFAULT_LIMIT = 20;

const GraphLabels: React.FC = () => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  
  const label = useSettingsStore((s) => s.queryLabel);
  const setQueryLabel = useSettingsStore((s) => s.setQueryLabel);
  
  const incrementGraphDataVersion = useGraphStore((s) => s.incrementGraphDataVersion);
  const setGraphDataFetchAttempted = useGraphStore((s) => s.setGraphDataFetchAttempted);
  const setLastSuccessfulQueryLabel = useGraphStore((s) => s.setLastSuccessfulQueryLabel);
  const setTypeColorMap = useGraphStore((s) => s.setTypeColorMap);
  
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [selectKey, setSelectKey] = useState(0);

  // 初始化搜索历史
  useEffect(() => {
    const initializeHistory = async () => {
      const history = SearchHistoryManager.getHistory();
      
      if (history.length === 0) {
        try {
          const popularLabels = await getPopularLabels(POPULAR_LABELS_DEFAULT_LIMIT);
          await SearchHistoryManager.initializeWithDefaults(popularLabels);
        } catch (error) {
          console.error('Failed to initialize search history:', error);
        }
      }
    };

    initializeHistory();
  }, []);

  // 标签变化时强制刷新下拉框
  useEffect(() => {
    setSelectKey(prev => prev + 1);
  }, [label]);

  // 获取下拉选项数据
  const fetchData = useCallback(
    async (query?: string): Promise<string[]> => {
      let results: string[] = [];
      
      if (!query || query.trim() === '' || query.trim() === '*') {
        // 空查询：返回搜索历史
        results = SearchHistoryManager.getHistoryLabels(DROPDOWN_DISPLAY_LIMIT);
      } else {
        // 非空查询：调用后端搜索 API
        try {
          const apiResults = await searchLabels(query.trim(), SEARCH_LABELS_DEFAULT_LIMIT);
          results = apiResults.length <= DROPDOWN_DISPLAY_LIMIT
            ? apiResults
            : [...apiResults.slice(0, DROPDOWN_DISPLAY_LIMIT), '...'];
        } catch (error) {
          console.error('Search API failed, falling back to local history:', error);
          
          // 降级到本地历史搜索
          const queryLower = query.toLowerCase().trim();
          results = SearchHistoryManager.getHistory()
            .filter(item => item.label.toLowerCase().includes(queryLower))
            .map(item => item.label)
            .slice(0, DROPDOWN_DISPLAY_LIMIT);
        }
      }
      
      // 始终在顶部显示 '*'
      const finalResults = ['*', ...results.filter(l => l !== '*')];
      return finalResults;
    },
    [refreshTrigger] // 依赖 refreshTrigger 以触发重新加载
  );

  // 处理刷新 - 重置为默认值 '*' 并刷新全局数据
  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    
    // 清除图例缓存
    setTypeColorMap(new Map<string, string>());

    try {
      // 始终重置为 '*' 并刷新全局数据
      // Debug: console.log('Refreshing: resetting to * and reloading global data');
      
      // 重置标签为 '*'
      setQueryLabel('*');
      
      // 重新加载热门标签
      try {
        const popularLabels = await getPopularLabels(POPULAR_LABELS_DEFAULT_LIMIT);
        SearchHistoryManager.clearHistory();
        
        if (popularLabels.length === 0) {
          const fallbackLabels = ['entity', 'relationship', 'document', 'concept'];
          await SearchHistoryManager.initializeWithDefaults(fallbackLabels);
        } else {
          await SearchHistoryManager.initializeWithDefaults(popularLabels);
        }
      } catch (error) {
        console.error('Failed to reload popular labels:', error);
        const fallbackLabels = ['entity', 'relationship', 'document'];
        SearchHistoryManager.clearHistory();
        await SearchHistoryManager.initializeWithDefaults(fallbackLabels);
      }
      
      // 重置图数据获取状态
      setGraphDataFetchAttempted(false);
      setLastSuccessfulQueryLabel('');
      
      // 强制图重新渲染
      incrementGraphDataVersion();
      
      // 触发下拉框刷新
      setRefreshTrigger(prev => prev + 1);
      setSelectKey(prev => prev + 1);
    } catch (error) {
      console.error('Error during refresh:', error);
    } finally {
      setIsRefreshing(false);
    }
  }, [incrementGraphDataVersion, setGraphDataFetchAttempted, setLastSuccessfulQueryLabel, setQueryLabel, setTypeColorMap]);

  // 处理下拉框打开前
  const handleDropdownBeforeOpen = useCallback(async () => {
    // 可选：重新加载热门标签
  }, []);

  // 处理标签选择
  const handleChange = useCallback((newLabel: string) => {
    const currentLabel = label;

    // 选择最后一项 '...' 表示查询全部
    if (newLabel === '...') {
      newLabel = '*';
    }

    // 重复选择同一标签（非 '*'）时，切换到 '*'
    if (newLabel === currentLabel && newLabel !== '*') {
      newLabel = '*';
    }

    // 添加到搜索历史（排除特殊情况）
    if (newLabel && newLabel !== '*' && newLabel !== '...' && newLabel.trim() !== '') {
      SearchHistoryManager.addToHistory(newLabel);
    }

    // 重置获取标志
    setGraphDataFetchAttempted(false);

    // 更新标签以触发数据加载
    setQueryLabel(newLabel);

    // 强制图重新渲染
    incrementGraphDataVersion();
  }, [label, incrementGraphDataVersion, setGraphDataFetchAttempted, setQueryLabel]);

  // 动态工具提示
  const getRefreshTooltip = useCallback(() => {
    if (isRefreshing) {
      return t('pages.knowledge.graph.refreshing') || '刷新中...';
    }
    // 刷新按钮始终重置为 '*' 并刷新全局数据
    return t('pages.knowledge.graph.refreshGlobal') || '重置并刷新全局数据';
  }, [t, isRefreshing]);

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      {/* 刷新按钮 */}
      <Tooltip title={getRefreshTooltip()}>
        <Button
          type="text"
          icon={<RefreshCw size={16} className={isRefreshing ? 'animate-spin' : ''} />}
          onClick={handleRefresh}
          disabled={isRefreshing}
          style={{
            color: token.colorPrimary,
            borderColor: token.colorBorder
          }}
        />
      </Tooltip>

      {/* 标签选择器 */}
      <div style={{ minWidth: 280, maxWidth: 500, flex: 1 }}>
        <AsyncSelect<string>
          key={selectKey}
          fetcher={fetchData}
          onBeforeOpen={handleDropdownBeforeOpen}
          renderOption={(item) => (
            <div style={{ 
              overflow: 'hidden', 
              textOverflow: 'ellipsis', 
              whiteSpace: 'nowrap',
              color: '#ffffff'
            }} title={item}>
              {item}
            </div>
          )}
          getOptionValue={(item) => item}
          getDisplayValue={(item) => (
            <div style={{ 
              minWidth: 0, 
              flex: 1, 
              overflow: 'hidden', 
              textOverflow: 'ellipsis', 
              textAlign: 'left' 
            }} title={item}>
              {item}
            </div>
          )}
          notFound={<div style={{ padding: '24px 0', textAlign: 'center', fontSize: 14 }}>
            {t('pages.knowledge.graph.noLabels') || '无标签'}
          </div>}
          ariaLabel={t('graphPanel.search.labelSearch.placeholder', '搜索节点名称')}
          placeholder={t('graphPanel.search.labelSearch.placeholder', '搜索节点名称...')}
          searchPlaceholder={t('graphPanel.search.labelSearch.searchInDropdown', '搜索节点名称...')}
          noResultsMessage={t('graphPanel.search.labelSearch.noResults', '无结果')}
          value={label !== null ? label : '*'}
          onChange={handleChange}
          clearable={false}
          debounceTime={500}
        />
      </div>
    </div>
  );
};

export default GraphLabels;
