import React from 'react';
import { logger } from '../../utils/logger';
import { Editor } from '../../modules/skill-editor';
import styled from '@emotion/styled';
import { IPCAPI } from '@/services/ipc/api';

const EditorContainer = styled.div`
  height: 100%;
  width: 100%;

  .doc-free-feature-overview {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  .demo-free-layout-tools {
    position: absolute;
    bottom: 10px;
    color: black;
  }
`;

const SkillEditor: React.FC = () => {
    return (
        <EditorContainer>
            <style>
                {`
                    .ant-layout-content {
                        padding: 2px !important;
                        margin: 2px !important;
                    }
                `}
            </style>
            <Editor />
        </EditorContainer>
    );
};

export default SkillEditor; 