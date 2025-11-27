import React from 'react';
import { Checkbox, InputNumber, Divider } from 'antd';
import { useTranslation } from 'react-i18next';
import { useSettingsStore } from '../stores/settings';

const SettingsPanel: React.FC = () => {
  const { t } = useTranslation();
  
  const showPropertyPanel = useSettingsStore((s) => s.showPropertyPanel);
  const showNodeSearchBar = useSettingsStore((s) => s.showNodeSearchBar);
  const showNodeLabel = useSettingsStore((s) => s.showNodeLabel);
  const enableNodeDrag = useSettingsStore((s) => s.enableNodeDrag);
  const showEdgeLabel = useSettingsStore((s) => s.showEdgeLabel);
  const enableHideUnselectedEdges = useSettingsStore((s) => s.enableHideUnselectedEdges);
  const enableEdgeEvents = useSettingsStore((s) => s.enableEdgeEvents);
  const minEdgeSize = useSettingsStore((s) => s.minEdgeSize);
  const maxEdgeSize = useSettingsStore((s) => s.maxEdgeSize);
  const graphQueryMaxDepth = useSettingsStore((s) => s.graphQueryMaxDepth);
  const graphMaxNodes = useSettingsStore((s) => s.graphMaxNodes);
  const graphLayoutMaxIterations = useSettingsStore((s) => s.graphLayoutMaxIterations);

  return (
    <div style={{
      background: 'rgba(45, 55, 72, 0.95)',
      backdropFilter: 'blur(12px)',
      border: '2px solid rgba(255, 255, 255, 0.1)',
      borderRadius: 12,
      padding: 16,
      width: 320,
      maxHeight: '80vh',
      overflowY: 'auto',
      boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
      color: '#ffffff'
    }}>
      {/* 显示选项 */}
      <div style={{ marginBottom: 16 }}>
        <Checkbox
          checked={showPropertyPanel}
          onChange={(e) => useSettingsStore.setState({ showPropertyPanel: e.target.checked })}
        >
          {t('graphPanel.settings.showPropertyPanel', '显示属性面板')}
        </Checkbox>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Checkbox
          checked={showNodeSearchBar}
          onChange={(e) => useSettingsStore.setState({ showNodeSearchBar: e.target.checked })}
        >
          {t('graphPanel.settings.showSearchBar', '显示搜索栏')}
        </Checkbox>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Checkbox
          checked={showNodeLabel}
          onChange={(e) => useSettingsStore.setState({ showNodeLabel: e.target.checked })}
        >
          {t('graphPanel.settings.showNodeLabel', '显示节点标签')}
        </Checkbox>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Checkbox
          checked={enableNodeDrag}
          onChange={(e) => useSettingsStore.setState({ enableNodeDrag: e.target.checked })}
        >
          {t('graphPanel.settings.enableNodeDrag', '节点可拖动')}
        </Checkbox>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Checkbox
          checked={showEdgeLabel}
          onChange={(e) => useSettingsStore.setState({ showEdgeLabel: e.target.checked })}
        >
          {t('graphPanel.settings.showEdgeLabel', '显示边标签')}
        </Checkbox>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Checkbox
          checked={enableHideUnselectedEdges}
          onChange={(e) => useSettingsStore.setState({ enableHideUnselectedEdges: e.target.checked })}
        >
          {t('graphPanel.settings.hideUnselectedEdges', '隐藏未选中的边')}
        </Checkbox>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Checkbox
          checked={enableEdgeEvents}
          onChange={(e) => useSettingsStore.setState({ enableEdgeEvents: e.target.checked })}
        >
          {t('graphPanel.settings.edgeEvents', '边事件')}
        </Checkbox>
      </div>

      <Divider style={{ margin: '12px 0' }} />

      {/* 边粗细范围 */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 13, marginBottom: 8, fontWeight: 500 }}>
          {t('graphPanel.settings.edgeThicknessRange', '边粗细范围')}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <InputNumber
            min={1}
            max={10}
            value={minEdgeSize}
            onChange={(value) => useSettingsStore.setState({ minEdgeSize: value || 1 })}
            style={{ width: 80 }}
          />
          <span>-</span>
          <InputNumber
            min={1}
            max={10}
            value={maxEdgeSize}
            onChange={(value) => useSettingsStore.setState({ maxEdgeSize: value || 4 })}
            style={{ width: 80 }}
          />
        </div>
      </div>

      <Divider style={{ margin: '12px 0' }} />

      {/* 最大查询深度 */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 13, marginBottom: 8, fontWeight: 500 }}>
          {t('graphPanel.settings.maxQueryDepth', '最大查询深度')}
        </div>
        <InputNumber
          min={1}
          max={10}
          value={graphQueryMaxDepth}
          onChange={(value) => useSettingsStore.setState({ graphQueryMaxDepth: value || 1 })}
          style={{ width: '100%' }}
        />
      </div>

      {/* 最大返回节点数 */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 13, marginBottom: 8, fontWeight: 500 }}>
          {t('graphPanel.settings.maxNodes', '最大返回节点数 (≤ 1000)')}
        </div>
        <InputNumber
          min={1}
          max={1000}
          value={graphMaxNodes}
          onChange={(value) => useSettingsStore.setState({ graphMaxNodes: value || 400 })}
          style={{ width: '100%' }}
        />
      </div>

      {/* 最大布局迭代次数 */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 13, marginBottom: 8, fontWeight: 500 }}>
          {t('graphPanel.settings.maxLayoutIterations', '最大布局迭代次数')}
        </div>
        <InputNumber
          min={1}
          max={1000}
          value={graphLayoutMaxIterations}
          onChange={(value) => useSettingsStore.setState({ graphLayoutMaxIterations: value || 200 })}
          style={{ width: '100%' }}
        />
      </div>

    </div>
  );
};

export default SettingsPanel;
