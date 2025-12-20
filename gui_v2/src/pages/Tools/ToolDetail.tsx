import React, { useRef } from 'react';
import { useEffectOnActive } from 'keepalive-for-react';
import { Descriptions, Empty } from 'antd';
import { Tool } from './types';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';

interface ToolDetailProps {
  tool: Tool | null;
}

const DetailContent = styled.div`
  width: 100%;
  height: 100%;
  overflow-y: auto;
  padding: 16px;
`;

const ToolDetail: React.FC<ToolDetailProps> = ({ tool }) => {
  const { t } = useTranslation();
  
  // ScrollPositionSave
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const savedScrollPositionRef = useRef<number>(0);
  
  // 使用 useEffectOnActive 在ComponentActive时RestoreScrollPosition
  useEffectOnActive(
    () => {
      const container = scrollContainerRef.current;
      if (container && savedScrollPositionRef.current > 0) {
        requestAnimationFrame(() => {
          container.scrollTop = savedScrollPositionRef.current;
        });
      }
      
      return () => {
        const container = scrollContainerRef.current;
        if (container) {
          savedScrollPositionRef.current = container.scrollTop;
        }
      };
    },
    []
  );
  
  if (!tool) return <Empty description={t('pages.tools.selectTool')} />;
  return (
    <DetailContent ref={scrollContainerRef}>
      <Descriptions title={tool.name} bordered column={1}>
        <Descriptions.Item label={t('pages.tools.description')}>{tool.description}</Descriptions.Item>
        <Descriptions.Item label={t('pages.tools.inputSchema')}>
          <pre style={{ whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(tool.inputSchema, null, 2)}
          </pre>
        </Descriptions.Item>
        <Descriptions.Item label={t('pages.tools.outputSchema')}>
          <pre style={{ whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(tool.outputSchema, null, 2)}
          </pre>
        </Descriptions.Item>
      </Descriptions>
    </DetailContent>
  );
};

export default ToolDetail; 