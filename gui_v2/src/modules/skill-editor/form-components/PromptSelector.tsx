import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Select, Button, Tooltip } from '@douyinfe/semi-ui';
import { IconEdit } from '@douyinfe/semi-icons';
import type { SelectProps } from '@douyinfe/semi-ui/lib/es/select';
import { usePromptStore } from '../../../stores/promptStore';
import { useUserStore } from '../../../stores/userStore';
import type { Prompt } from '../../../pages/Prompts/types';

interface PromptSelectorProps extends Omit<SelectProps, 'value' | 'onChange'> {
  value?: string; // This will be the prompt ID or 'in-line'
  onChange?: (value: string) => void;
  promptType?: 'systemPrompt' | 'prompt';
}

const IN_LINE_PROMPT_ID = 'in-line';

export const PromptSelector: React.FC<PromptSelectorProps> = ({
  value,
  onChange,
  promptType = 'prompt',
  ...rest
}) => {
  const username = useUserStore((s) => s.username || 'user');
  const { prompts, fetch, fetched } = usePromptStore();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!fetched) {
      setLoading(true);
      fetch(username).finally(() => setLoading(false));
    }
  }, [fetched, fetch, username]);

  const options = useMemo(() => {
    const promptOptions = prompts.map((p: Prompt) => ({
      label: `${p.source === 'sample_prompts' ? 'sample' : 'my'}:${p.title}`,
      value: p.id,
    }));
    return [
      { label: 'In-line Prompt', value: IN_LINE_PROMPT_ID },
      ...promptOptions,
    ];
  }, [prompts]);

  const navigate = useNavigate();

  const handleEditPrompt = () => {
    if (value && value !== IN_LINE_PROMPT_ID) {
      navigate(`/prompts?id=${encodeURIComponent(value)}&edit=true`);
    }
  };

  const showEditButton = value && value !== IN_LINE_PROMPT_ID;

  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'center', width: '100%' }}>
      <Select
        value={value || IN_LINE_PROMPT_ID}
        onChange={(v) => onChange?.(v as string)}
        optionList={options}
        loading={loading}
        placeholder={`Select a ${promptType === 'systemPrompt' ? 'system' : 'user'} prompt`}
        style={{ flex: 1 }}
        {...rest}
      />
      {showEditButton && (
        <Tooltip content="Edit prompt">
          <Button
            icon={<IconEdit />}
            size="small"
            theme="borderless"
            onClick={handleEditPrompt}
            style={{ flexShrink: 0 }}
          />
        </Tooltip>
      )}
    </div>
  );
};

export { IN_LINE_PROMPT_ID };
