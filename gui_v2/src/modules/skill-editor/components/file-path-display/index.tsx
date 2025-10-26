/**
 * File Path Display Component
 * Shows current file path and unsaved changes indicator
 */

import React from 'react';
import { Tooltip, Tag, Space } from '@douyinfe/semi-ui';
import { IconFile, IconEdit } from '@douyinfe/semi-icons';
import styled from 'styled-components';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import { hasFullFilePaths } from '../../../../config/platform';

const FilePathContainer = styled.div`
  position: absolute;
  top: 10px;
  left: 10px;
  background-color: rgba(255, 255, 255, 0.98);
  padding: 8px 12px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  z-index: 1000;
  max-width: 400px;
  border: 1px solid rgba(0, 0, 0, 0.1);
`;

const FilePathText = styled.div`
  font-size: 12px;
  color: #666;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 300px;
`;

const SkillNameText = styled.div`
  font-size: 14px;
  font-weight: 600;
  color: #333;
  margin-bottom: 2px;
`;

const StatusContainer = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
`;

/**
 * Extract file name from full path
 */
function getFileName(filePath: string): string {
  if (!filePath) return '';
  const parts = filePath.replace(/\\/g, '/').split('/');
  return parts[parts.length - 1] || '';
}

/**
 * Extract directory path from full path
 */
function getDirectoryPath(filePath: string): string {
  if (!filePath) return '';
  const parts = filePath.replace(/\\/g, '/').split('/');
  return parts.slice(0, -1).join('/') || '';
}

export const FilePathDisplay: React.FC = () => {
  const currentFilePath = useSkillInfoStore((state) => state.currentFilePath);
  const hasUnsavedChanges = useSkillInfoStore((state) => state.hasUnsavedChanges);
  const skillInfo = useSkillInfoStore((state) => state.skillInfo);

  // Only show if we have full file path support (desktop mode)
  if (!hasFullFilePaths()) {
    return null;
  }

  // Don't show if no file is loaded
  if (!currentFilePath && !skillInfo) {
    return null;
  }

  const fileName = currentFilePath ? getFileName(currentFilePath) : 'Untitled';
  const directoryPath = currentFilePath ? getDirectoryPath(currentFilePath) : '';
  const skillName = skillInfo?.skillName || 'Untitled Skill';

  return (
    <FilePathContainer>
      <StatusContainer>
        <Space>
          <IconFile size="small" style={{ color: '#666' }} />
          <div>
            <SkillNameText>
              {skillName}
              {hasUnsavedChanges && (
                <Tooltip content="Unsaved changes">
                  <IconEdit 
                    size="small" 
                    style={{ 
                      color: '#ff6b35', 
                      marginLeft: '4px',
                      verticalAlign: 'middle'
                    }} 
                  />
                </Tooltip>
              )}
            </SkillNameText>
            {currentFilePath ? (
              <Tooltip 
                content={currentFilePath}
                position="bottomLeft"
              >
                <FilePathText>
                  {directoryPath && `${directoryPath}/`}
                  <strong>{fileName}</strong>
                </FilePathText>
              </Tooltip>
            ) : (
              <FilePathText>
                <em>Not saved to file</em>
              </FilePathText>
            )}
          </div>
        </Space>
        
        {hasUnsavedChanges && (
          <Tag 
            color="orange" 
            size="small"
            style={{ fontSize: '10px' }}
          >
            Modified
          </Tag>
        )}
      </StatusContainer>
    </FilePathContainer>
  );
};

export default FilePathDisplay;
