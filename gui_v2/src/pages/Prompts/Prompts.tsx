import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import DetailLayout from '../../components/Layout/DetailLayout';
import PromptsList from './PromptsList';
import PromptsDetail from './PromptsDetail';
import type { Prompt } from './types';
import { usePromptStore } from '../../stores/promptStore';
import { useUserStore } from '../../stores/userStore';
import { useTranslation } from 'react-i18next';

const Prompts: React.FC = () => {
  const username = useUserStore((s) => s.username || 'user');
  const { t } = useTranslation();
  const { prompts, fetch, save, clone, fetched } = usePromptStore();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [searchParams, setSearchParams] = useSearchParams();
  const [initialEditMode, setInitialEditMode] = useState(false);

  // Handle URL params for direct navigation to a specific prompt in edit mode
  useEffect(() => {
    const urlPromptId = searchParams.get('id');
    const urlEdit = searchParams.get('edit');
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
      }
    });
  };

  const handleRefresh = () => {
    fetch(username, true);
  };

  return (
    <DetailLayout
      listTitle={null}
      detailsTitle={selected ? selected.title : t('pages.prompts.details')}
      listContent={
        <PromptsList
          prompts={filtered}
          selectedId={selectedId}
          onSelect={setSelectedId}
          search={search}
          onSearchChange={setSearch}
          onAdd={handleAdd}
          onDelete={handleDelete}
          onRefresh={handleRefresh}
          onClone={handleClone}
        />
      }
      detailsContent={
        <PromptsDetail
          prompt={selected}
          onChange={handleChange}
          initialEditMode={initialEditMode}
          onEditModeConsumed={() => setInitialEditMode(false)}
        />
      }
    />
  );
};

export default Prompts;
