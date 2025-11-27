import React, { useEffect, useState } from 'react';
import { theme, Tooltip, message } from 'antd';
import { useTranslation } from 'react-i18next';
import { useGraphStore, RawNodeType, RawEdgeType } from '../stores/graph';
import { PropertyName, PropertyValue } from './PropertyRowComponents';
import EditablePropertyRow from './EditablePropertyRow';
import { BranchesOutlined, ScissorOutlined } from '@ant-design/icons';
import { expandNode as expandNodeApi, pruneNode as pruneNodeApi } from '../api/lightrag';

const PropertiesView: React.FC = () => {
  const { token } = theme.useToken();
  const { t } = useTranslation();
  
  const selectedNode = useGraphStore(s => s.selectedNode);
  const focusedNode = useGraphStore(s => s.focusedNode);
  const selectedEdge = useGraphStore(s => s.selectedEdge);
  const focusedEdge = useGraphStore(s => s.focusedEdge);
  const rawGraph = useGraphStore(s => s.rawGraph);

  const [currentElement, setCurrentElement] = useState<NodeType | EdgeType | null>(null);
  const [currentType, setCurrentType] = useState<'node' | 'edge' | null>(null);

  useEffect(() => {
    let type: 'node' | 'edge' | null = null;
    let element: RawNodeType | RawEdgeType | null = null;

    if (!rawGraph) return;

    if (focusedNode) {
      type = 'node';
      element = rawGraph.getNode(focusedNode);
    } else if (selectedNode) {
      type = 'node';
      element = rawGraph.getNode(selectedNode);
    } else if (focusedEdge) {
      type = 'edge';
      element = rawGraph.getEdge(focusedEdge, true);
    } else if (selectedEdge) {
      type = 'edge';
      element = rawGraph.getEdge(selectedEdge, true);
    }

    if (element) {
      if (type === 'node') {
        setCurrentElement(refineNodeProperties(element as RawNodeType));
      } else {
        setCurrentElement(refineEdgeProperties(element as RawEdgeType));
      }
      setCurrentType(type);
    } else {
      setCurrentElement(null);
      setCurrentType(null);
    }
  }, [focusedNode, selectedNode, focusedEdge, selectedEdge, rawGraph]);

  if (!currentElement) return null;

  return (
    <div style={{
      background: 'rgba(45, 55, 72, 0.95)',
      border: '2px solid rgba(255, 255, 255, 0.1)',
      borderRadius: 12,
      padding: 12,
      fontSize: 12,
      width: 320,
      maxHeight: '80vh',
      overflow: 'auto',
      color: '#ffffff',
      boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
      backdropFilter: 'blur(12px)',
      position: 'absolute',
      top: 16,
      right: 16,
      zIndex: 10
    }}>
      {currentType === 'node' ? (
        <NodePropertiesView node={currentElement as NodeType} />
      ) : (
        <EdgePropertiesView edge={currentElement as EdgeType} />
      )}
    </div>
  );
};

type NodeType = RawNodeType & {
  relationships: {
    type: string;
    id: string;
    label: string;
    edgeLabel?: string;
    direction?: 'outgoing' | 'incoming';
  }[];
};

type EdgeType = RawEdgeType & {
  sourceNode?: RawNodeType;
  targetNode?: RawNodeType;
};

const refineNodeProperties = (node: RawNodeType): NodeType => {
  const state = useGraphStore.getState();
  const relationships: any[] = [];

  if (state.sigmaGraph && state.rawGraph) {
    try {
      if (!state.sigmaGraph.hasNode(node.id)) {
        console.log('[PropertiesView] Node not in sigma graph:', node.id);
        return { ...node, relationships: [] };
      }

      const edges = state.sigmaGraph.edges(node.id);
      console.log('[PropertiesView] Node edges:', node.id, edges);
      
      for (const edgeId of edges) {
        console.log('[PropertiesView] Processing edge:', edgeId);
        
        if (!state.sigmaGraph.hasEdge(edgeId)) {
          console.log('[PropertiesView] Edge not in sigma graph:', edgeId);
          continue;
        }
        
        const edge = state.rawGraph.getEdge(edgeId, true);
        console.log('[PropertiesView] Edge data:', edge);
        
        if (!edge) {
          console.log('[PropertiesView] Edge not found in rawGraph:', edgeId);
          continue;
        }
        
        const isSource = node.id === edge.source;
        const neighbourId = isSource ? edge.target : edge.source;
        console.log('[PropertiesView] Neighbour ID:', neighbourId, 'isSource:', isSource);
        
        if (!state.sigmaGraph.hasNode(neighbourId)) {
          console.log('[PropertiesView] Neighbour not in sigma graph:', neighbourId);
          continue;
        }
        
        const neighbour = state.rawGraph.getNode(neighbourId);
        console.log('[PropertiesView] Neighbour data:', neighbour);
        
        if (!neighbour) {
          console.log('[PropertiesView] Neighbour not found in rawGraph:', neighbourId);
          continue;
        }
        
        const relationLabel = edge.properties?.keywords || edge.type || '关系';
        relationships.push({
          type: isSource ? '邻接' : '邻接',
          id: neighbourId,
          label: neighbour.properties['entity_id'] || neighbour.labels.join(', '),
          edgeLabel: relationLabel,
          direction: isSource ? 'outgoing' : 'incoming'
        });
        console.log('[PropertiesView] Added relationship:', relationships[relationships.length - 1]);
      }
      
      console.log('[PropertiesView] Relationships found:', relationships.length, relationships);
    } catch (e) {
      console.error('Error refining node properties:', e);
    }
  }

  return { ...node, relationships };
};

const refineEdgeProperties = (edge: RawEdgeType): EdgeType => {
  const state = useGraphStore.getState();
  let sourceNode: RawNodeType | undefined;
  let targetNode: RawNodeType | undefined;

  if (state.sigmaGraph && state.rawGraph) {
    try {
       if (state.sigmaGraph.hasNode(edge.source)) {
         sourceNode = state.rawGraph.getNode(edge.source);
       }
       if (state.sigmaGraph.hasNode(edge.target)) {
         targetNode = state.rawGraph.getNode(edge.target);
       }
    } catch (e) {
      console.error('Error refining edge properties:', e);
    }
  }
  
  return { ...edge, sourceNode, targetNode };
};

const PropertyRow = ({
  name,
  value,
  onClick,
  tooltip,
  nodeId,
  edgeId,
  dynamicId,
  entityId,
  entityType,
  sourceId,
  targetId,
  isEditable = false,
  truncate
}: {
  name: string;
  value: any;
  onClick?: () => void;
  tooltip?: string;
  nodeId?: string;
  entityId?: string;
  edgeId?: string;
  dynamicId?: string;
  entityType?: 'node' | 'edge';
  sourceId?: string;
  targetId?: string;
  isEditable?: boolean;
  truncate?: string;
}) => {
  const { t } = useTranslation();
  
  const formatValueWithSeparators = (val: any): string => {
    if (typeof val === 'string') return val.replace(/<SEP>/g, ';\n');
    return typeof val === 'string' ? val : JSON.stringify(val, null, 2);
  };

  const formattedValue = formatValueWithSeparators(value);
  let formattedTooltip = tooltip || formatValueWithSeparators(value);
  if (name === 'source_id' && truncate) {
    formattedTooltip += `\n(Truncated: ${truncate})`;
  }

  if (isEditable && (name === 'description' || name === 'entity_id' || name === 'entity_type' || name === 'keywords')) {
    return (
      <EditablePropertyRow
        name={name}
        value={value}
        onClick={onClick}
        nodeId={nodeId}
        entityId={entityId}
        edgeId={edgeId}
        dynamicId={dynamicId}
        entityType={entityType}
        sourceId={sourceId}
        targetId={targetId}
        isEditable={true}
        tooltip={tooltip || (typeof value === 'string' ? value : JSON.stringify(value, null, 2))}
      />
    );
  }

  const { token } = theme.useToken();
  
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, overflow: 'hidden' }}>
      <PropertyName name={name} />
      <span style={{ color: token.colorTextSecondary }}>:</span>
      <PropertyValue
        value={formattedValue}
        onClick={onClick}
        tooltip={formattedTooltip}
      />
    </div>
  );
};

const NodePropertiesView = ({ node }: { node: NodeType }) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const [expanding, setExpanding] = useState(false);
  const [pruning, setPruning] = useState(false);

  const handleExpandNode = async () => {
    setExpanding(true);
    try {
      const result = await expandNodeApi(String(node.id), 1, 50);
      if (result && (result.nodes.length > 0 || result.edges.length > 0)) {
        // 添加新节点和边到图中
        const store = useGraphStore.getState();
        if (store.rawGraph && store.sigmaGraph) {
          // 合并新数据到现有图中
          result.nodes.forEach((n: any) => {
            if (!store.rawGraph!.hasNode(n.id)) {
              store.rawGraph!.addNode(n.id, n);
            }
          });
          result.edges.forEach((e: any) => {
            if (!store.rawGraph!.hasEdge(e.id)) {
              store.rawGraph!.addEdge(e.id, e);
            }
          });
          // 触发图更新
          store.setRawGraph(store.rawGraph);
        }
        message.success(t('graphPanel.propertiesView.node.expandSuccess', `已扩展 ${result.nodes.length} 个节点`));
      } else {
        message.info(t('graphPanel.propertiesView.node.noMoreNodes', '没有更多节点可扩展'));
      }
    } catch (e: any) {
      message.error(t('graphPanel.propertiesView.node.expandError', '扩展节点失败') + ': ' + (e?.message || ''));
    } finally {
      setExpanding(false);
    }
  };
  
  const handlePruneNode = async () => {
    setPruning(true);
    try {
      const result = await pruneNodeApi(String(node.id));
      if (result.success) {
        // 从图中移除节点
        const store = useGraphStore.getState();
        if (store.rawGraph && store.sigmaGraph) {
          if (store.rawGraph.hasNode(node.id)) {
            store.rawGraph.removeNode(node.id);
          }
          // 触发图更新
          store.setRawGraph(store.rawGraph);
          store.setSelectedNode(null);
        }
        message.success(t('graphPanel.propertiesView.node.pruneSuccess', '节点已移除'));
      } else {
        message.error(result.message || t('graphPanel.propertiesView.node.pruneError', '移除节点失败'));
      }
    } catch (e: any) {
      message.error(t('graphPanel.propertiesView.node.pruneError', '移除节点失败') + ': ' + (e?.message || ''));
    } finally {
      setPruning(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ margin: 0, color: token.colorPrimary, fontWeight: 600 }}>
          {t('graphPanel.propertiesView.node.title', 'Node Details')}
        </h3>
        <div style={{ display: 'flex', gap: 4 }}>
          <Tooltip title={t('graphPanel.propertiesView.node.expandNode', 'Expand Node')}>
            <button className="ec-icon-btn" onClick={handleExpandNode}>
              <BranchesOutlined />
            </button>
          </Tooltip>
          <Tooltip title={t('graphPanel.propertiesView.node.pruneNode', 'Prune Node')}>
            <button className="ec-icon-btn" onClick={handlePruneNode}>
              <ScissorOutlined />
            </button>
          </Tooltip>
        </div>
      </div>

      <div style={{ background: 'rgba(0,0,0,0.02)', padding: 8, borderRadius: 6, display: 'flex', flexDirection: 'column', gap: 4 }}>
        <PropertyRow name={t('graphPanel.propertiesView.node.id', 'ID')} value={String(node.id)} />
        <PropertyRow name={t('graphPanel.propertiesView.node.labels', 'Labels')} value={node.labels.join(', ')} />
        <PropertyRow name={t('graphPanel.propertiesView.node.degree', 'Degree')} value={node.degree} />
      </div>

      <h3 style={{ margin: 0, color: token.colorWarning, fontWeight: 600 }}>
        {t('graphPanel.propertiesView.node.properties', 'Properties')}
      </h3>
      <div style={{ background: 'rgba(0,0,0,0.02)', padding: 8, borderRadius: 6, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {Object.keys(node.properties)
          .sort()
          .map((name) => {
             if (name === 'created_at' || name === 'truncate') return null;
             return (
               <PropertyRow
                 key={name}
                 name={name}
                 value={node.properties[name]}
                 nodeId={String(node.id)}
                 entityId={node.properties['entity_id']}
                 entityType="node"
                 isEditable={name === 'description' || name === 'entity_id' || name === 'entity_type'}
                 truncate={node.properties['truncate']}
               />
             );
          })}
      </div>

      {node.relationships.length > 0 && (
        <>
          <h3 style={{ margin: 0, color: token.colorSuccess, fontWeight: 600 }}>
            {t('graphPanel.propertiesView.node.relationshipsInSubgraph', '关系（子图内）')}
          </h3>
          <div style={{ background: 'rgba(0,0,0,0.02)', padding: 8, borderRadius: 6, display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 200, overflow: 'auto' }}>
            {node.relationships.map(({ type, id, label, edgeLabel, direction }, index) => (
              <div key={`${id}-${index}`} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                  <PropertyName name={type} />
                  <span style={{ color: token.colorTextSecondary }}>:</span>
                  <PropertyValue
                    value={label}
                    onClick={() => useGraphStore.getState().setSelectedNode(id, true)}
                    tooltip={label}
                  />
                </div>
                {edgeLabel && (
                  <div style={{ 
                    fontSize: 11, 
                    color: token.colorTextTertiary, 
                    paddingLeft: 12,
                    fontStyle: 'italic'
                  }}>
                    {edgeLabel}
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
      
      <style>{`
        .ec-icon-btn {
          background: transparent;
          border: 1px solid ${token.colorBorder};
          border-radius: 4px;
          cursor: pointer;
          padding: 2px 6px;
          color: ${token.colorTextSecondary};
          transition: all 0.2s;
        }
        .ec-icon-btn:hover {
          background: ${token.colorBgTextHover};
          color: ${token.colorText};
        }
      `}</style>
    </div>
  );
};

const EdgePropertiesView = ({ edge }: { edge: EdgeType }) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <h3 style={{ margin: 0, color: token.colorError, fontWeight: 600 }}>
        {t('graphPanel.propertiesView.edge.title', 'Edge Details')}
      </h3>
      <div style={{ background: 'rgba(0,0,0,0.02)', padding: 8, borderRadius: 6, display: 'flex', flexDirection: 'column', gap: 4 }}>
        <PropertyRow name={t('graphPanel.propertiesView.edge.id', 'ID')} value={edge.id} />
        {edge.type && <PropertyRow name={t('graphPanel.propertiesView.edge.type', 'Type')} value={edge.type} />}
        <PropertyRow
          name={t('graphPanel.propertiesView.edge.source', 'Source')}
          value={edge.sourceNode ? edge.sourceNode.labels.join(', ') : edge.source}
          onClick={() => useGraphStore.getState().setSelectedNode(edge.source, true)}
        />
        <PropertyRow
          name={t('graphPanel.propertiesView.edge.target', 'Target')}
          value={edge.targetNode ? edge.targetNode.labels.join(', ') : edge.target}
          onClick={() => useGraphStore.getState().setSelectedNode(edge.target, true)}
        />
      </div>

      <h3 style={{ margin: 0, color: token.colorWarning, fontWeight: 600 }}>
        {t('graphPanel.propertiesView.edge.properties', 'Properties')}
      </h3>
      <div style={{ background: 'rgba(0,0,0,0.02)', padding: 8, borderRadius: 6, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {Object.keys(edge.properties)
          .sort()
          .map((name) => {
             if (name === 'created_at' || name === 'truncate') return null;
             return (
               <PropertyRow
                 key={name}
                 name={name}
                 value={edge.properties[name]}
                 edgeId={String(edge.id)}
                 dynamicId={String(edge.dynamicId)}
                 entityType="edge"
                 sourceId={edge.sourceNode?.properties['entity_id'] || edge.source}
                 targetId={edge.targetNode?.properties['entity_id'] || edge.target}
                 isEditable={name === 'description' || name === 'keywords'}
                 truncate={edge.properties['truncate']}
               />
             );
          })}
      </div>
    </div>
  );
};

export default PropertiesView;
