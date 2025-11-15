import React, { Suspense, lazy } from 'react';
import { useTranslation } from 'react-i18next';
const LazyEditor = lazy(async () => {
  const mod = await import('../../modules/skill-editor');
  return { default: mod.Editor } as any;
});
import styled from '@emotion/styled';
import { SkillLogPanel } from '../../modules/skill-editor/components/log/SkillLogPanel';

const EditorContainer = styled.div`
  height: 100%;
  width: 100%;
  display: flex;
  flex-direction: column;

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
    const { t } = useTranslation();
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
            <div style={{ flex: 1, minHeight: 0 }}>
            <Suspense fallback={
                <div style={{
                    height: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'var(--text-secondary)'
                }}>
                    {t('pages.skills.loadingEditor') || 'Loading editor...'}
                </div>
            }>
                <LazyEditor />
            </Suspense>
            </div>
            <SkillLogPanel />
        </EditorContainer>
    );
};

export default SkillEditor;