import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import PromptsList from './PromptsList';
import PromptsDetail from './PromptsDetail';
import PromptsPageLayout from './PromptsPageLayout';
import PromptAgentChat from './components/PromptAgentChat';
import type { Prompt, PromptAgentChatMessage } from './types';
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
      sections: [
        {
          id: `role-${Date.now()}`,
          type: 'role',
          items: [
            'You are an experienced after-sales customer support agent. You handle return requests, refund inquiries, product complaints, and shipping issues with professionalism and empathy.',
          ],
        },
        {
          id: `goals-${Date.now() + 1}`,
          type: 'goals',
          items: [
            'Resolve customer issues efficiently while maintaining a positive customer experience.',
            'Accurately categorize and escalate issues that require human intervention.',
            'Collect all necessary information before processing returns or refunds.',
          ],
        },
        {
          id: `guidelines-${Date.now() + 2}`,
          type: 'guidelines',
          items: [
            'Always greet the customer and acknowledge their concern before troubleshooting.',
            'Verify order details (order ID, product, purchase date) before taking any action.',
            'Follow the company return/refund policy strictly — refunds within 30 days, exchanges within 60 days.',
          ],
        },
        {
          id: `instructions-${Date.now() + 3}`,
          type: 'instructions',
          items: [
            'Step 1: Identify the customer issue type (return, refund, complaint, shipping, other).',
            'Step 2: Look up the relevant order and verify eligibility based on policy.',
            'Step 3: Execute the appropriate action (initiate return, process refund, escalate) using the available tools.',
            'Step 4: Confirm the resolution with the customer and provide a reference/tracking number.',
          ],
        },
        {
          id: `rules-${Date.now() + 4}`,
          type: 'rules',
          items: [
            'Always respond with a structured JSON data including at least these k-v pairs: { "all_done": true/false, "tools": [{"tool_name": string, "tool_input": {}}...] }. If all work is done, make sure to set "all_done" to true. If we encountered errors and cannot continue, add an "error" k-v pair to the response data, but still make sure to set "all_done" to true to exit the entire task.',
          ],
        },
        {
          id: `exceptions-${Date.now() + 5}`,
          type: 'exceptions',
          items: [
            'If the order is older than 60 days, politely decline and suggest contacting support for special review.',
            'If the customer reports a safety issue, escalate immediately — do not attempt to resolve independently.',
            'If payment gateway errors occur during refund processing, retry once then escalate to the finance team.',
          ],
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

  // ── Prompt agent chat wiring ────────────────────────────────────
  // The chat panel proposes mdContent edits; when the user clicks
  // Apply, we switch the prompt into Markdown mode and overwrite
  // mdContent. The chat history persists alongside the prompt JSON
  // (see prompt_handler._serialize_prompt_for_storage).
  const handleApplyProposedChange = useCallback(
    (proposedMd: string) => {
      if (!selected || selected.readOnly) return;
      const next: Prompt = {
        ...selected,
        format: 'md',
        mdContent: proposedMd,
        lastModified: new Date().toISOString(),
      };
      save(username, next);
    },
    [selected, username, save]
  );

  const handleChatHistoryChange = useCallback(
    (history: PromptAgentChatMessage[]) => {
      if (!selected) return;
      // Skip writes when nothing actually changed (initial sync).
      const before = selected.agentChatHistory || [];
      if (
        before.length === history.length &&
        before.every((m, i) => m.id === history[i]?.id && m.content === history[i]?.content)
      ) {
        return;
      }
      const next: Prompt = {
        ...selected,
        agentChatHistory: history,
        lastModified: new Date().toISOString(),
      };
      save(username, next);
    },
    [selected, username, save]
  );

  return (
    <PromptsPageLayout
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
          splitLayout
        />
      }
      chatContent={
        <PromptAgentChat
          prompt={selected}
          onApplyProposedChange={handleApplyProposedChange}
          onHistoryChange={handleChatHistoryChange}
        />
      }
    />
  );
};

export default Prompts;
