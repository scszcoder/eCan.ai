import React, { useState, useCallback, useEffect } from 'react';
import { Layout, Typography, Card } from 'antd';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import ActionButtons from '../components/Common/ActionButtons';
import {ipc_api} from '../services/ipc_api';

const { Content } = Layout;
const { Title } = Typography;

const ToolsContainer = styled(Layout)`
  height: calc(100vh - 112px);
  background: transparent;
`;

const ToolsContent = styled(Content)`
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
`;

const ToolsHeader = styled.div`
  padding: 16px;
  background: #fff;
  border-radius: 4px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
`;

const ToolsMain = styled.div`
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
`;

const ToolsList = styled(Card)`
  width: 280px;
  .ant-card-body {
    padding: 0;
    height: 100%;
  }
`;

const ToolsDetails = styled(Card)`
  flex: 1;
  .ant-card-body {
    padding: 0;
    height: 100%;
  }
`;

interface Tool {
    id: number;
    name: string;
    type: string;
    status: 'active' | 'maintenance' | 'offline';
    battery: number;
    location: string;
    lastMaintenance: string;
    totalDistance: number;
    currentTask?: string;
    nextMaintenance?: string;
}

const toolsEventBus = {
    listeners: new Set<(data: Tool[]) => void>(),
    subscribe(listener: (data: Tool[]) => void) {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    },
    emit(data: Tool[]) {
        this.listeners.forEach(listener => listener(data));
    }
};

// 导出更新数据的函数
export const updateToolsGUI = (data: Tool[]) => {
    toolsEventBus.emit(data);
};

const Tools: React.FC = () => {
  const { t } = useTranslation();

  return (
    <ToolsContainer>
      <ToolsContent>
        <ToolsHeader>
          <Title level={4} style={{ margin: 0 }}>{t('pages.tools.title')}</Title>
        </ToolsHeader>
        <ToolsMain>
          <ToolsList title={t('pages.tools.list')} variant="borderless">
            {/* Tools list will be implemented here */}
          </ToolsList>
          <ToolsDetails variant="borderless">
            {/* Tools details will be implemented here */}
            <ActionButtons
                onAdd={() => {}}
                onEdit={() => {}}
                onDelete={() => {}}
                onRefresh={() => {}}
                onExport={() => {}}
                onImport={() => {}}
                onSettings={() => {}}
                addText={t('pages.tools.addTool')}
                editText={t('pages.tools.editTool')}
                deleteText={t('pages.tools.deleteTool')}
                refreshText={t('pages.tools.refreshTools')}
                exportText={t('pages.tools.exportTools')}
                importText={t('pages.tools.importTools')}
                settingsText={t('pages.tools.toolSettings')}
            />
          </ToolsDetails>
        </ToolsMain>
      </ToolsContent>
    </ToolsContainer>
  );
};

export default Tools; 