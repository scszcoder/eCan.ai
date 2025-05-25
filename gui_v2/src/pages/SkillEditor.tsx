import React from 'react';
import { logger } from '../utils/logger';
import { SkEditor } from '../modules/skill-editor';
import styled from '@emotion/styled';

const EditorContainer = styled.div`
  height: 100%;
  width: 100%;
  padding: 1px;
  background: #fff;

  .doc-free-feature-overview {
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  .demo-container {
    flex: 1;
    display: flex;
    position: relative;
    overflow: hidden;
  }

  .demo-editor {
    flex: 1;
    position: relative;
  }
`;

const SkillEditor: React.FC = () => {
    return (
        <EditorContainer>
            <style>
                {`
                    .ant-layout-content {
                        padding: 3px !important;
                        margin: 3px !important;
                    }
                `}
            </style>
            <SkEditor />
        </EditorContainer>
    );
};

export default SkillEditor; 