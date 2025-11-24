import React, { useEffect, useState } from 'react';
import { theme, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { useGraphStore, RawNodeType, RawEdgeType } from '../stores/graph';
import { PropertyName, PropertyValue } from './PropertyRowComponents';
import EditablePropertyRow from './EditablePropertyRow';
import { BranchesOutlined, ScissorOutlined } from '@ant-design/icons';

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
      background: token.colorBgElevated,
      border: `1px solid ${token.colorBorder}`,
      borderRadius: 12,
      padding: 12,
      fontSize: 12,
      width: 320,
      maxHeight: '80vh',
      overflow: 'auto',
      color: token.colorText,
      boxShadow: token.boxShadowSecondary,
      backdropFilter: 'blur(8px)',
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
        return { ...node, relationships: [] };
      }

      const edges = state.sigmaGraph.edges(node.id);
      for (const edgeId of edges) {
        if (!state.sigmaGraph.hasEdge(edgeId)) continue;
        const edge = state.rawGraph.getEdge(edgeId, true);
        if (edge) {
          const isTarget = node.id === edge.source;
          const neighbourId = isTarget ? edge.target : edge.source;
          if (!state.sigmaGraph.hasNode(neighbourId)) continue;
          
          const neighbour = state.rawGraph.getNode(neighbourId);
          if (neighbour) {
             relationships.push({
                type: 'Neighbour',
                id: neighbourId,
                label: neighbour.properties['entity_id'] || neighbour.labels.join(', ')
             });
          }
        }
      }
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

  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, overflow: 'hidden' }}>
      <PropertyName name={name} />
      <span style={{ color: 'rgba(0,0,0,0.45)' }}>:</span>
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

  const handleExpandNode = () => {
    console.log('Expand node not implemented yet');
  };
  
  const handlePruneNode = () => {
     console.log('Prune node not implemented yet');
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
            {t('graphPanel.propertiesView.node.relationships', 'Relationships')}
          </h3>
          <div style={{ background: 'rgba(0,0,0,0.02)', padding: 8, borderRadius: 6, display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 200, overflow: 'auto' }}>
            {node.relationships.map(({ type, id, label }) => (
              <PropertyRow
                key={id}
                name={type}
                value={label}
                onClick={() => useGraphStore.getState().setSelectedNode(id, true)}
              />
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
