import React, { Suspense, lazy, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
const LazyEditor = lazy(async () => {
  const start = performance.now();
  console.time('[Perf][SkillEditorPage] LazyEditor import');
  const mod = await import('../../modules/skill-editor');
  console.timeEnd('[Perf][SkillEditorPage] LazyEditor import');
  console.log('[Perf][SkillEditorPage] LazyEditor import duration:', `${(performance.now() - start).toFixed(1)}ms`);
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
    const pageMountPerfRef = useRef<number>(performance.now());
    const [translationsReady, setTranslationsReady] = useState(false);

    // Dynamically load skill-editor translations when component mounts
    useEffect(() => {
        console.log('[Perf][SkillEditorPage] Page mounted');
        const loadSkillEditorTranslations = async () => {
            // Avoid loading multiple times
            if (translationsLoadedRef.current) {
                setTranslationsReady(true);
                return;
            }
            
            try {
                const translationStart = performance.now();
                console.time('[Perf][SkillEditorPage] Translation load');

                // Dynamically import translation files
                const [enSkillEditor, zhSkillEditor] = await Promise.all([
                    import('../../modules/skill-editor/i18n/en.json'),
                    import('../../modules/skill-editor/i18n/zh.json'),
                ]);

                // Always merge latest skill editor bundles so newly added keys are available
                i18n.addResourceBundle('en-US', 'skillEditor', enSkillEditor.default, true, true);
                i18n.addResourceBundle('zh-CN', 'skillEditor', zhSkillEditor.default, true, true);

                translationsLoadedRef.current = true;
                setTranslationsReady(true);
                console.timeEnd('[Perf][SkillEditorPage] Translation load');
                console.log('[Perf][SkillEditorPage] Translation load duration:', `${(performance.now() - translationStart).toFixed(1)}ms`);
                console.log('[SkillEditor] Translations loaded successfully');
            } catch (error) {
                console.error('[SkillEditor] Failed to load translations:', error);
                setTranslationsReady(true);
            }
        };

        loadSkillEditorTranslations();

        return () => {
            console.log('[Perf][SkillEditorPage] Page lifetime:', `${(performance.now() - pageMountPerfRef.current).toFixed(1)}ms`);
        };
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
            {translationsReady ? (
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
            ) : (
                <div style={{
                    height: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'var(--text-secondary)'
                }}>
                    {t('pages.skills.loadingEditor') || 'Loading editor...'}
                </div>
            )}
            </div>
            <SkillConsolePanel />
        </EditorContainer>
    );
};

export default SkillEditor;