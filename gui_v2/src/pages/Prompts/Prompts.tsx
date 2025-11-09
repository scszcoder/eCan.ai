import React, { useEffect, useMemo, useState } from 'react';
import DetailLayout from '../../components/Layout/DetailLayout';
import PromptsList from './PromptsList';
import PromptsDetail from './PromptsDetail';
import type { Prompt } from './types';
import { usePromptStore } from '../../stores/promptStore';
import { useUserStore } from '../../stores/userStore';

const Prompts: React.FC = () => {
  const username = useUserStore((s) => s.username || 'user');
  const { prompts, fetch, save, fetched } = usePromptStore();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState('');

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
    const newId = `pr-${Math.floor(Math.random() * 100000)}`;
    const np: Prompt = {
      id: newId,
      title: 'New Prompt',
      topic: 'New prompt',
      usageCount: 0,
      roleToneContext: '',
      goals: [],
      guidelines: [],
      rules: [],
      instructions: [],
      sysInputs: [],
      humanInputs: [],
    };
    save(username, np).then(() => setSelectedId(newId));
  };

  const handleDelete = (id: string) => {
    usePromptStore.getState().remove(username, id).then(() => {
      if (selectedId === id) setSelectedId(null);
    });
  };

  return (
    <DetailLayout
      listTitle={null}
      detailsTitle={selected ? selected.title : 'Details'}
      listContent={
        <PromptsList
          prompts={filtered}
          selectedId={selectedId}
          onSelect={setSelectedId}
          search={search}
          onSearchChange={setSearch}
          onAdd={handleAdd}
          onDelete={handleDelete}
        />
      }
      detailsContent={<PromptsDetail prompt={selected} onChange={handleChange} />}
    />
  );
};

export default Prompts;
