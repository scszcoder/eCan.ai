import { FC, useCallback, useEffect } from 'react';
import AsyncSearch from './AsyncSearch';
import { useGraphStore } from '../stores/graph';
import MiniSearch from 'minisearch';
import { useTranslation } from 'react-i18next';

const searchResultLimit = 20;

export interface OptionItem {
  id: string;
  type: 'nodes' | 'message';
  message?: string;
}

const NodeOption = ({ id }: { id: string }) => {
  const graph = useGraphStore((s) => s.sigmaGraph);

  if (!graph?.hasNode(id)) {
    return null;
  }

  const label = graph.getNodeAttribute(id, 'label') || id;
  const color = graph.getNodeAttribute(id, 'color') || '#666';

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
      <div
        style={{
          width: 12,
          height: 12,
          borderRadius: '50%',
          backgroundColor: color,
          flexShrink: 0,
          border: '1px solid rgba(255, 255, 255, 0.2)'
        }}
      />
      <span style={{ 
        fontSize: 13, 
        overflow: 'hidden', 
        textOverflow: 'ellipsis', 
        whiteSpace: 'nowrap',
        color: '#ffffff',
        flex: 1
      }}>
        {label}
      </span>
    </div>
  );
};

function OptionComponent(item: OptionItem) {
  return (
    <div>
      {item.type === 'nodes' && <NodeOption id={item.id} />}
      {item.type === 'message' && <div style={{ fontSize: 12, color: 'rgba(255, 255, 255, 0.6)' }}>{item.message}</div>}
    </div>
  );
}

interface GraphSearchProps {
  value?: OptionItem | null;
  onChange?: (value: OptionItem | null) => void;
  onFocus?: (value: OptionItem | null) => void;
}

const GraphSearch: FC<GraphSearchProps> = ({ value, onChange, onFocus }) => {
  const { t } = useTranslation();
  const graph = useGraphStore((s) => s.sigmaGraph);
  const searchEngine = useGraphStore((s) => s.searchEngine);

  // Reset search engine when graph changes
  useEffect(() => {
    if (graph) {
      useGraphStore.getState().resetSearchEngine();
    }
  }, [graph]);

  // Create search engine when needed
  useEffect(() => {
    if (!graph || graph.nodes().length === 0 || searchEngine) {
      return;
    }

    const newSearchEngine = new MiniSearch({
      idField: 'id',
      fields: ['label'],
      searchOptions: {
        prefix: true,
        fuzzy: 0.2,
        boost: {
          label: 2
        }
      }
    });

    const documents = graph.nodes()
      .filter(id => graph.hasNode(id))
      .map((id: string) => ({
        id: id,
        label: graph.getNodeAttribute(id, 'label')
      }));

    if (documents.length > 0) {
      newSearchEngine.addAll(documents);
    }

    useGraphStore.getState().setSearchEngine(newSearchEngine);
  }, [graph, searchEngine]);

  const loadOptions = useCallback(
    async (query?: string): Promise<OptionItem[]> => {
      if (onFocus) onFocus(null);

      if (!graph || !searchEngine) {
        return [];
      }

      if (graph.nodes().length === 0) {
        return [];
      }

      // If no query, return some nodes
      if (!query) {
        const nodeIds = graph.nodes()
          .filter(id => graph.hasNode(id))
          .slice(0, searchResultLimit);
        return nodeIds.map(id => ({
          id,
          type: 'nodes'
        }));
      }

      // Search nodes
      let result: OptionItem[] = searchEngine.search(query)
        .filter((r: { id: string }) => graph.hasNode(r.id))
        .map((r: { id: string }) => ({
          id: r.id,
          type: 'nodes'
        }));

      // Add middle-content matching if results are few
      if (result.length < 5) {
        const matchedIds = new Set(result.map(item => item.id));
        const middleMatchResults = graph.nodes()
          .filter(id => {
            if (matchedIds.has(id)) return false;
            if (!graph.hasNode(id)) return false;
            const label = graph.getNodeAttribute(id, 'label');
            return label &&
                   typeof label === 'string' &&
                   !label.toLowerCase().startsWith(query.toLowerCase()) &&
                   label.toLowerCase().includes(query.toLowerCase());
          })
          .map(id => ({
            id,
            type: 'nodes' as const
          }));

        result = [...result, ...middleMatchResults];
      }

      return result.length <= searchResultLimit
        ? result
        : [
          ...result.slice(0, searchResultLimit),
          {
            type: 'message',
            id: '__message__',
            message: t('pages.knowledge.graph.moreResults', { count: result.length - searchResultLimit }) || `还有 ${result.length - searchResultLimit} 个结果...`
          }
        ];
    },
    [graph, searchEngine, onFocus, t]
  );

  return (
    <AsyncSearch
      className="w-full"
      fetcher={loadOptions}
      renderOption={OptionComponent}
      getOptionValue={(item) => item.id}
      value={value && value.type !== 'message' ? value.id : null}
      onChange={(id) => {
        if (id !== '__message__') onChange?.(id ? { id, type: 'nodes' } : null);
      }}
      onFocus={(id) => {
        if (id !== '__message__' && onFocus) onFocus(id ? { id, type: 'nodes' } : null);
      }}
      ariaLabel={t('graphPanel.search.nodeSearch.placeholder', '页面内搜索节点')}
      placeholder={t('graphPanel.search.nodeSearch.placeholder', '页面内搜索节点...')}
      noResultsMessage={t('graphPanel.search.nodeSearch.noResults', '无结果')}
    />
  );
};

export default GraphSearch;
