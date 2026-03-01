import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Tabs, Button, Space, Tooltip } from 'antd';
import {
  EditOutlined,
  BulbOutlined,
  ThunderboltOutlined,
  BookOutlined,
} from '@ant-design/icons';
import DetailLayout from '../../components/Layout/DetailLayout';
import PromptsList from './PromptsList';
import PromptsDetail from './PromptsDetail';
import PromptGuide from './components/PromptGuide';
import PromptTemplates from './components/PromptTemplates';
import PromptExamples from './components/PromptExamples';
import type { Prompt } from './types';
import { usePromptStore } from '../../stores/promptStore';
import { useUserStore } from '../../stores/userStore';
import { useTranslation } from 'react-i18next';
import styles from './PromptsEnhanced.module.css';

const PromptsEnhanced: React.FC = () => {
  const username = useUserStore((s) => s.username || 'user');
  const { t } = useTranslation();
  const { prompts, fetch, save, clone, fetched } = usePromptStore();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [searchParams, setSearchParams] = useSearchParams();
  const [initialEditMode, setInitialEditMode] = useState(false);
  const [activeTab, setActiveTab] = useState<string>('editor');

  // Handle URL params for direct navigation to a specific prompt in edit mode
  useEffect(() => {
    const urlPromptId = searchParams.get('id');
    const urlEdit = searchParams.get('edit');
    const urlTab = searchParams.get('tab');
    
    if (urlTab) {
      setActiveTab(urlTab);
    }
    
    if (urlPromptId && fetched) {
      const exists = prompts.some(p => p.id === urlPromptId);
      if (exists) {
        setSelectedId(urlPromptId);
        if (urlEdit === 'true') {
          setInitialEditMode(true);
        }
        // Clear the URL params after applying them
        setSearchParams({}, { replace: true });
      }
    }
  }, [searchParams, fetched, prompts, setSearchParams]);

  useEffect(() => {
    if (!fetched) fetch(username);
  }, [fetched, fetch, username]);

  useEffect(() => {
    if (!selectedId && prompts.length > 0) setSelectedId(prompts[0].id);
  }, [prompts, selectedId]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return prompts;
    return prompts.filter(p =>
      p.title.toLowerCase().includes(q) ||
      p.topic.toLowerCase().includes(q)
    );
  }, [prompts, search]);

  const selected = useMemo(() => prompts.find(p => p.id === selectedId) ?? null, [prompts, selectedId]);

  const handleChange = (np: Prompt) => {
    save(username, np);
  };

  const handleAdd = () => {
    const newId = `pr-${Math.floor(Math.random() * 1_000_000)}`;
    const np: Prompt = {
      id: newId,
      title: t('pages.prompts.newPrompt'),
      topic: t('pages.prompts.newPrompt'),
      usageCount: 0,
      sections: [],
      userSections: [],
      humanInputs: [],
      source: 'my_prompts',
      readOnly: false,
    };
    save(username, np).then((saved) => {
      if (saved) {
        setSelectedId(saved.id);
        setActiveTab('editor');
      }
    });
  };

  const handleDelete = (id: string) => {
    usePromptStore.getState().remove(username, id).then(() => {
      if (selectedId === id) setSelectedId(null);
    });
  };

  const handleClone = (prompt: Prompt) => {
    clone(username, prompt).then((copied) => {
      if (copied) {
        setSelectedId(copied.id);
        setActiveTab('editor');
      }
    });
  };

  const handleRefresh = () => {
    fetch(username, true);
  };

  const handleUseTemplate = (template: any) => {
    // Create a new prompt from template
    const newId = `pr-${Math.floor(Math.random() * 1_000_000)}`;
    const np: Prompt = {
      id: newId,
      title: template.title,
      topic: template.description,
      usageCount: 0,
      sections: [
        {
          id: 'template-content',
          type: 'instructions',
          items: [template.template],
        },
      ],
      userSections: [],
      humanInputs: [],
      source: 'my_prompts',
      readOnly: false,
    };
    save(username, np).then((saved) => {
      if (saved) {
        setSelectedId(saved.id);
        setActiveTab('editor');
        setInitialEditMode(true);
      }
    });
  };

  const tabItems = [
    {
      key: 'editor',
      label: (
        <Space>
          <EditOutlined />
          {t('pages.prompts.tabs.editor', { defaultValue: '编辑器' })}
        </Space>
      ),
      children: (
        <PromptsDetail
          prompt={selected}
          onChange={handleChange}
          initialEditMode={initialEditMode}
          onEditModeConsumed={() => setInitialEditMode(false)}
        />
      ),
    },
    {
      key: 'guide',
      label: (
        <Space>
          <BulbOutlined />
          {t('pages.prompts.tabs.guide', { defaultValue: '设计指南' })}
        </Space>
      ),
      children: <PromptGuide />,
    },
    {
      key: 'templates',
      label: (
        <Space>
          <ThunderboltOutlined />
          {t('pages.prompts.tabs.templates', { defaultValue: '模板库' })}
        </Space>
      ),
      children: <PromptTemplates onUseTemplate={handleUseTemplate} />,
    },
    {
      key: 'examples',
      label: (
        <Space>
          <BookOutlined />
          {t('pages.prompts.tabs.examples', { defaultValue: '示例库' })}
        </Space>
      ),
      children: <PromptExamples />,
    },
  ];

  const detailsTitle = useMemo(() => {
    if (activeTab === 'guide') {
      return t('pages.prompts.tabs.guide', { defaultValue: '设计指南' });
    }
    if (activeTab === 'templates') {
      return t('pages.prompts.tabs.templates', { defaultValue: '模板库' });
    }
    if (activeTab === 'examples') {
      return t('pages.prompts.tabs.examples', { defaultValue: '示例库' });
    }
    return selected ? selected.title : t('pages.prompts.details');
  }, [activeTab, selected, t]);

  const detailsExtra = useMemo(() => {
    if (activeTab !== 'editor') return null;
    
    return (
      <Space size={8}>
        <Tooltip title={t('pages.prompts.tabs.guide', { defaultValue: '设计指南' })}>
          <Button
            type="text"
            size="small"
            icon={<BulbOutlined />}
            onClick={() => setActiveTab('guide')}
          >
            {t('pages.prompts.viewGuide', { defaultValue: '查看指南' })}
          </Button>
        </Tooltip>
        <Tooltip title={t('pages.prompts.tabs.templates', { defaultValue: '模板库' })}>
          <Button
            type="text"
            size="small"
            icon={<ThunderboltOutlined />}
            onClick={() => setActiveTab('templates')}
          >
            {t('pages.prompts.useTemplate', { defaultValue: '使用模板' })}
          </Button>
        </Tooltip>
      </Space>
    );
  }, [activeTab, t]);

  return (
    <DetailLayout
      listTitle={null}
      detailsTitle={detailsTitle}
      listContent={
        <PromptsList
          prompts={filtered}
          selectedId={selectedId}
          onSelect={(id) => {
            setSelectedId(id);
            setActiveTab('editor');
          }}
          search={search}
          onSearchChange={setSearch}
          onAdd={handleAdd}
          onDelete={handleDelete}
          onRefresh={handleRefresh}
          onClone={handleClone}
        />
      }
      detailsContent={
        <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={tabItems}
            style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
            tabBarStyle={{ marginBottom: 0, paddingLeft: 20, paddingRight: 20, background: '#0f172a', flex: '0 0 auto' }}
            className={styles.promptsTabs}
          />
        </div>
      }
    />
  );
};

export default PromptsEnhanced;
