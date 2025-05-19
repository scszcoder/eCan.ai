import React from 'react';
import { Card, Typography } from 'antd';
import styled from '@emotion/styled';

const { Title } = Typography;

const SkillEditorContainer = styled.div`
    display: flex;
    gap: 16px;
    height: 100%;
`;

const EditorPanel = styled(Card)`
    flex: 1;
    height: 100%;
    overflow: auto;
`;

const PreviewPanel = styled(Card)`
    flex: 1;
    height: 100%;
    overflow: auto;
`;

const SkillEditor: React.FC = () => {
    return (
        <SkillEditorContainer>
            <EditorPanel variant="borderless" title="Skill Editor">
                <Title level={4}>Skill Editor Content</Title>
                {/* Add editor content here */}
            </EditorPanel>
            <PreviewPanel variant="borderless" title="Preview">
                <Title level={4}>Preview Content</Title>
                {/* Add preview content here */}
            </PreviewPanel>
        </SkillEditorContainer>
    );
};

export default SkillEditor; 