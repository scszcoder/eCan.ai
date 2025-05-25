import React from 'react';
import { Card, Typography } from 'antd';
import { logger } from '../utils/logger';
import { Editor } from '../modules/skill-editor/editor';

const { Title } = Typography;

const SkillEditor: React.FC = () => {
    logger.debug('SkillEditor component rendered');

    return (
        // <Editor></Editor>
        <Card>
            <Title level={2}>Skill Editor</Title>
            <p>Skill editor content will be implemented here.</p>
        </Card>
    );
};

export default SkillEditor; 