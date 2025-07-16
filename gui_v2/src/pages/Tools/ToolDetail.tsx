import React from 'react';
import { Descriptions, Empty } from 'antd';
import { Tool } from './types';
import styled from '@emotion/styled';

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
  if (!tool) return <Empty description="请选择工具" />;
  return (
    <DetailContent>
      <Descriptions title={tool.name} bordered column={1}>
        <Descriptions.Item label="描述">{tool.description}</Descriptions.Item>
        <Descriptions.Item label="输入Schema">
          <pre style={{ whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(tool.inputSchema, null, 2)}
          </pre>
        </Descriptions.Item>
        <Descriptions.Item label="输出Schema">
          <pre style={{ whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(tool.outputSchema, null, 2)}
          </pre>
        </Descriptions.Item>
      </Descriptions>
    </DetailContent>
  );
};

export default ToolDetail; 