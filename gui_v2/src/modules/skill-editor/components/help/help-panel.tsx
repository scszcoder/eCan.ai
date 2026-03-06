/**
 * Help Panel: side overlay with search and documentation
 */
import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SideSheet, Input, Nav, Button } from '@douyinfe/semi-ui';
import { IconSearch, IconClose } from '@douyinfe/semi-icons';

interface HelpPanelProps {
  visible: boolean;
  onCancel: () => void;
}

export const HelpPanel: React.FC<HelpPanelProps> = ({ visible, onCancel }) => {
  const { t } = useTranslation('skillEditor');
  const [selectedKey, setSelectedKey] = useState<string>('intro');
  const [query, setQuery] = useState<string>('');

  const docToc = useMemo(() => [
    { key: 'intro',     text: t('helpPanel.toc.intro') },
    { key: 'nodes',     text: t('helpPanel.toc.nodes') },
    { key: 'editor',    text: t('helpPanel.toc.editor') },
    { key: 'debug',     text: t('helpPanel.toc.debug') },
    { key: 'testrun',   text: t('helpPanel.toc.testrun') },
    { key: 'shortcuts', text: t('helpPanel.toc.shortcuts') },
    { key: 'faq',       text: t('helpPanel.toc.faq') },
  ], [t]);

  const docSections = useMemo((): Record<string, React.ReactNode> => ({
    intro: (
      <div>
        <h2>{t('helpPanel.sections.intro.title')}</h2>
        <p>{t('helpPanel.sections.intro.content')}</p>
      </div>
    ),
    nodes: (
      <div>
        <h2>{t('helpPanel.sections.nodes.title')}</h2>
        <p>{t('helpPanel.sections.nodes.content')}</p>
      </div>
    ),
    editor: (
      <div>
        <h2>{t('helpPanel.sections.editor.title')}</h2>
        <p>{t('helpPanel.sections.editor.content')}</p>
      </div>
    ),
    debug: (
      <div>
        <h2>{t('helpPanel.sections.debug.title')}</h2>
        <p>{t('helpPanel.sections.debug.content')}</p>
      </div>
    ),
    testrun: (
      <div>
        <h2>{t('helpPanel.sections.testrun.title')}</h2>
        <p>{t('helpPanel.sections.testrun.content')}</p>
      </div>
    ),
    shortcuts: (
      <div>
        <h2>{t('helpPanel.sections.shortcuts.title')}</h2>
        <h3>{t('helpPanel.sections.shortcuts.navigation')}</h3>
        <ul>
          <li><strong>Space + Drag</strong>: {t('helpPanel.sections.shortcuts.spaceDrag')}</li>
          <li><strong>Mouse wheel</strong>: {t('helpPanel.sections.shortcuts.mouseWheel')}</li>
          <li><strong>Ctrl/Cmd + +</strong>: {t('helpPanel.sections.shortcuts.ctrlPlus')}</li>
          <li><strong>Ctrl/Cmd + -</strong>: {t('helpPanel.sections.shortcuts.ctrlMinus')}</li>
        </ul>
        <h3>{t('helpPanel.sections.shortcuts.editing')}</h3>
        <ul>
          <li><strong>Ctrl/Cmd + Z</strong>: {t('helpPanel.sections.shortcuts.ctrlZ')}</li>
          <li><strong>Ctrl/Cmd + Y</strong>: {t('helpPanel.sections.shortcuts.ctrlY')}</li>
          <li><strong>Ctrl/Cmd + C</strong>: {t('helpPanel.sections.shortcuts.ctrlC')}</li>
          <li><strong>Ctrl/Cmd + V</strong>: {t('helpPanel.sections.shortcuts.ctrlV')}</li>
          <li><strong>Ctrl/Cmd + A</strong>: {t('helpPanel.sections.shortcuts.ctrlA')}</li>
          <li><strong>Delete / Backspace</strong>: {t('helpPanel.sections.shortcuts.deleteKey')}</li>
        </ul>
        <h3>{t('helpPanel.sections.shortcuts.nodeOps')}</h3>
        <ul>
          <li><strong>Click</strong>: {t('helpPanel.sections.shortcuts.clickNode')}</li>
          <li><strong>Double-click</strong>: {t('helpPanel.sections.shortcuts.doubleClickNode')}</li>
          <li><strong>Drag</strong>: {t('helpPanel.sections.shortcuts.dragNode')}</li>
          <li><strong>Shift + Click</strong>: {t('helpPanel.sections.shortcuts.shiftClick')}</li>
        </ul>
      </div>
    ),
    faq: (
      <div>
        <h2>{t('helpPanel.sections.faq.title')}</h2>
        <p>{t('helpPanel.sections.faq.content')}</p>
      </div>
    ),
  }), [t]);

  const filteredToc = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return docToc;
    return docToc.filter(item => item.text.toLowerCase().includes(q));
  }, [query, docToc]);

  const content = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return docSections[selectedKey] || null;
    return (
      <div>
        <div style={{ marginBottom: 12, color: 'var(--semi-color-text-2)' }}>
          {t('helpPanel.showingResults')} <strong>{query}</strong>
        </div>
        {docSections[selectedKey]}
      </div>
    );
  }, [selectedKey, query, docSections, t]);

  return (
    <SideSheet
      visible={visible}
      onCancel={onCancel}
      closable={false}
      mask={true}
      width={800}
      headerStyle={{ display: 'none' }}
      bodyStyle={{ padding: 0 }}
      style={{ background: 'var(--semi-color-bg-1)', color: 'var(--semi-color-text-0)' }}
    >
      {/* Header with search and close */}
      <div style={{ display: 'flex', alignItems: 'center', padding: 12, gap: 8, borderBottom: '1px solid var(--semi-color-border)', background: 'var(--semi-color-bg-1)' }}>
        <Input
          prefix={<IconSearch />}
          placeholder={t('helpPanel.searchPlaceholder')}
          value={query}
          onChange={setQuery}
        />
        <Button icon={<IconClose />} type="tertiary" theme="borderless" onClick={onCancel} />
      </div>

      {/* Content area split: left TOC, right doc */}
      <div style={{ display: 'flex', minHeight: 520 }}>
        <div style={{ width: 240, borderRight: '1px solid var(--semi-color-border)', padding: 12, color: 'var(--semi-color-text-0)' }}>
          <Nav
            selectedKeys={[selectedKey]}
            items={filteredToc.map(item => ({ itemKey: item.key, text: item.text }))}
            onSelect={data => setSelectedKey(String(data.itemKey))}
            style={{ width: '100%' }}
          />
        </div>
        <div style={{ flex: 1, padding: 16, overflow: 'auto', color: 'var(--semi-color-text-0)', lineHeight: 1.6 }}>
          <div style={{ maxWidth: 860 }}>
            {content}
          </div>
        </div>
      </div>
    </SideSheet>
  );
};
