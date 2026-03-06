import React, { Suspense, lazy, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
const LazyEditor = lazy(async () => {
  const mod = await import('../../modules/skill-editor');
  return { default: mod.Editor } as any;
});
import styled from '@emotion/styled';
import { SkillConsolePanel } from '../../modules/skill-editor/components/log/SkillConsolePanel';

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
    const { t, i18n } = useTranslation();
    const translationsLoadedRef = useRef(false);

    // Dynamically load skill-editor translations when component mounts
    useEffect(() => {
        const loadSkillEditorTranslations = async () => {
            // Avoid loading multiple times
            if (translationsLoadedRef.current) return;
            
            try {
                // Check if already loaded
                if (i18n.hasResourceBundle('en-US', 'skillEditor') && 
                    i18n.hasResourceBundle('zh-CN', 'skillEditor')) {
                    translationsLoadedRef.current = true;
                    return;
                }

                // Dynamically import translation files
                const [enSkillEditor, zhSkillEditor] = await Promise.all([
                    import('../../modules/skill-editor/i18n/en.json'),
                    import('../../modules/skill-editor/i18n/zh.json'),
                ]);

                // Add resource bundles to i18n
                if (!i18n.hasResourceBundle('en-US', 'skillEditor')) {
                    i18n.addResourceBundle('en-US', 'skillEditor', enSkillEditor.default, true, false);
                }
                if (!i18n.hasResourceBundle('zh-CN', 'skillEditor')) {
                    i18n.addResourceBundle('zh-CN', 'skillEditor', zhSkillEditor.default, true, false);
                }

                translationsLoadedRef.current = true;
                console.log('[SkillEditor] Translations loaded successfully');
            } catch (error) {
                console.error('[SkillEditor] Failed to load translations:', error);
            }
        };

        loadSkillEditorTranslations();
    }, [i18n]);
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
            <SkillConsolePanel />
        </EditorContainer>
    );
};

export default SkillEditor;